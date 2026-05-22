"""审核客户端模块 - 提供内容审核 API 的异步 HTTP 客户端。"""

import asyncio
from dataclasses import dataclass, field

import aiohttp
from astrbot.api import logger


@dataclass
class AuditResult:
    """审核结果数据类"""

    has_violation: bool = False
    """是否包含违规内容"""
    source: str = ""
    """审核来源"""
    request_id: str = ""
    """请求 ID"""
    error: str = ""
    """错误信息"""
    raw_response: dict = field(default_factory=dict)
    """原始响应数据"""


class AuditClient:
    """内容审核异步 HTTP 客户端"""

    def __init__(self, base_url: str, api_key: str, timeout: int = 10, max_retries: int = 3) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._session: aiohttp.ClientSession | None = None
        self._last_health_ok: bool = True
        self._last_health_time: float = 0.0
        self._health_fail_count: int = 0

    def update_base_url(self, base_url: str) -> None:
        new_url = base_url.rstrip("/")
        if new_url != self._base_url:
            self._base_url = new_url
            old_session = self._session
            self._session = None
            if old_session and not old_session.closed:
                asyncio.ensure_future(old_session.close())
            logger.info(f"审核客户端 base_url 已更新为: {new_url}")

    async def _get_session(self) -> aiohttp.ClientSession:
        """延迟初始化 HTTP 会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._session

    async def audit(self, text: str, skip_llm: bool = False) -> AuditResult:
        """
        审核文本内容

        Args:
            text: 待审核的文本内容
            skip_llm: 是否跳过 LLM 审核

        Returns:
            AuditResult: 审核结果
        """
        payload = {"sentence": text, "skip_llm": skip_llm}
        url = f"{self._base_url}/audit"

        for attempt in range(self._max_retries + 1):
            try:
                session = await self._get_session()
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
                    return AuditResult(
                        has_violation=data.get("has_violation", False),
                        source=data.get("source", ""),
                        request_id=data.get("request_id", ""),
                        raw_response=data,
                    )
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < self._max_retries:
                    delay = 2**attempt  # 指数退避: 1s, 2s, 4s, ...
                    logger.warning(f"审核请求失败, 第 {attempt + 1} 次重试, 等待 {delay}s: {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"审核请求失败, 已达最大重试次数: {e}")
                    return AuditResult(has_violation=False, error=str(e))

    async def health_check(self) -> dict | None:
        """
        健康检查

        Returns:
            dict | None: 健康检查结果, 失败时返回 None
        """
        url = f"{self._base_url}/health"
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                data = await resp.json()
                self._last_health_ok = True
                self._last_health_time = asyncio.get_event_loop().time()
                self._health_fail_count = 0
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            self._last_health_ok = False
            self._last_health_time = asyncio.get_event_loop().time()
            self._health_fail_count += 1
            logger.warning(f"健康检查失败: {e}")
            return None

    @property
    def health_status(self) -> dict:
        return {
            "ok": self._last_health_ok,
            "last_check_time": self._last_health_time,
            "fail_count": self._health_fail_count,
        }

    async def close(self) -> None:
        """关闭 HTTP 会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("审核客户端会话已关闭")

    async def __aenter__(self) -> "AuditClient":
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """异步上下文管理器出口"""
        await self.close()
        return None
