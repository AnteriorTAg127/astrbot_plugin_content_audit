# Issue 31 — `update_base_url()` 丢弃旧 session 而不关闭，造成连接泄露

**严重度**：🔴 Critical  
**涉及文件**：`audit_client.py`（行 39-45）  
**类型**：资源泄露

## 现象

当用户通过 AstrBot 管理面板修改 API 地址时，`update_base_url()` 被调用。它直接设置 `self._session = None` 来强制下次重建 session，但**没有关闭旧的 ClientSession**：

```python
def update_base_url(self, base_url: str) -> None:
    new_url = base_url.rstrip("/")
    if new_url != self._base_url:
        self._base_url = new_url
        self._session = None          # ← 旧 session 泄露！未 close()
        logger.info(f"审核客户端 base_url 已更新为: {new_url}")
```

`aiohttp.ClientSession` 内部维护连接池。不调用 `close()` 会导致：
1. 底层 TCP 连接不会被主动关闭，依赖服务端超时或 OS 级别的 socket 超时回收
2. 连接池中的空闲连接持续占用文件描述符
3. 在高频更新 base_url 的场景下（如反复修改配置测试），文件描述符可能被耗尽

## 问题分析

调用链：
```
健康检查回圈 (60s) → health_check() → _get_session() → 创建新 session
用户改配置 → _on_config_reload → update_base_url() → self._session = None (泄露旧 session)
下次消息审核 → audit() → _get_session() → 创建又一个新 session
```

每次 base_url 变更都泄露一个 `ClientSession`。虽然生产环境中 base_url 不会频繁变更，但在调试和运维过程中可能出现。

## 修复方案

在设置 `self._session = None` 之前，先关闭旧 session：

```python
def update_base_url(self, base_url: str) -> None:
    new_url = base_url.rstrip("/")
    if new_url != self._base_url:
        self._base_url = new_url
        old_session = self._session
        self._session = None
        if old_session and not old_session.closed:
            # 注意：不能在同步方法中 await，需要调度关闭
            asyncio.ensure_future(old_session.close())
        logger.info(f"审核客户端 base_url 已更新为: {new_url}")
```

或者更好的方案——改为异步方法：

```python
async def update_base_url(self, base_url: str) -> None:
    new_url = base_url.rstrip("/")
    if new_url != self._base_url:
        self._base_url = new_url
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        logger.info(f"审核客户端 base_url 已更新为: {new_url}")
```

同时需将 `main.py` 中的调用改为 `await`：

```python
def _on_config_reload(config: dict) -> None:
    api_cfg = config.get("api", {})
    new_url = api_cfg.get("base_url", "http://127.0.0.1:8000")
    if self._audit_client is not None:
        asyncio.ensure_future(self._audit_client.update_base_url(new_url))
```

**Why**：每个 `aiohttp.ClientSession` 都持有 TCP 连接池。关闭旧 session 确保底层 socket 被正确释放。使用 `ensure_future` 包装是因为 `_on_config_reload` 是同步回调，无法 `await`。

**How to apply**：修改 `audit_client.py` 的 `update_base_url()` 和 `main.py` 的回调。
