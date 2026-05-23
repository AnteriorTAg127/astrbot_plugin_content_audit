"""上下文缓存模块 — 按群缓存最近消息，用于审核 API 的 context 字段。"""

from collections import deque


class ContextCache:
    """群聊消息环形缓冲区

    每个群维护一个 bounded deque，自动淘汰旧消息。
    asyncio 单线程模型下无需锁。
    """

    def __init__(self) -> None:
        self._buffers: dict[str, deque[tuple[str, str]]] = {}

    def add(self, group_id: str, sender: str, text: str, maxlen: int) -> None:
        """追加一条消息到指定群的缓冲区。

        Args:
            group_id: 群号
            sender: 发送者昵称
            text: 消息文本（原始内容，内部会转义换行符）
            maxlen: 缓冲区最大长度，若与当前 dequeue 的 maxlen 不一致则自动 resize
        """
        if maxlen <= 0:
            return
        buf = self._buffers.get(group_id)
        if buf is None:
            buf = deque(maxlen=maxlen)
            self._buffers[group_id] = buf
        elif buf.maxlen is not None and buf.maxlen != maxlen:
            # maxlen 变更：重建 dequeue 以应用新容量
            items = list(buf)
            buf = deque(items, maxlen=maxlen)
            self._buffers[group_id] = buf
        buf.append((sender, text))

    def get_context(self, group_id: str, k: int) -> str:
        """取出最近 k 条消息，格式化为审核上下文字符串。

        消息内的换行符（\\\\n、\\\\r）被替换为空格，防止破坏上下文格式。
        若该群无缓存记录则返回空字符串。

        Args:
            group_id: 群号
            k: 取最近 k 条消息

        Returns:
            格式化的上下文字符串，示例：

            以下是最近 3 条消息

            张三：你好
            李四：今天天气不错
            王五：确实
        """
        if k <= 0:
            return ""
        buf = self._buffers.get(group_id)
        if not buf:
            return ""
        items = list(buf)[-k:]
        if not items:
            return ""

        # 最长 2000 字符（API 侧会再次截断，这里先做第一道兜底）
        header = f"以下是最近 {len(items)} 条消息"
        lines: list[str] = [header, ""]
        for sender, text in items:
            # 转义换行符，防止多行消息破坏上下文格式
            safe_text = text.replace("\r", "").replace("\n", " ")
            lines.append(f"{sender}：{safe_text}")

        full = "\n".join(lines)
        return full[:2000]

    def clear_group(self, group_id: str) -> None:
        """清空指定群的缓存。"""
        self._buffers.pop(group_id, None)
