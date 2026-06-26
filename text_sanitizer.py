"""文本清洗工具模块。

提供纯函数 ``strip_qq_in_at``，用于在送审 / 写上下文缓存之前剔除
OneBot/NapCat 协议中 ``@昵称(QQ号)`` 或 ``@昵称（QQ号）`` 形式里的 QQ 号。

- 纯函数，无副作用，不依赖 AstrBot 或其他模块
- O(n) 时间复杂度
- 支持半角 ``()`` 与全角 ``（）`` 及二者混搭
"""

import re

# 匹配 @<昵称>(<数字>) 或全角等任意组合：
#   - 昵称：1~32 个非空白、非括号、非 @ 的字符（防止贪婪误吞下一个 @）
#   - 括号：左右括号各自支持半角/全角 (左半右半、左全右全、左半右全、左全右半)
#   - 内容：1~20 位纯数字
_AT_QQ_PATTERN = re.compile(r"@([^\s()（）@]{1,32})[(（](\d{1,20})[)）]")

# 行内连续空白压缩：把"非换行的空白序列"压成单个空格
_INLINE_WS_PATTERN = re.compile(r"[^\S\n]+")

# 换行前后的空格清理：把 " \n" / "\n " / " \n " 等压成单个 "\n"
_NEWLINE_WS_PATTERN = re.compile(r"[^\S\n]*\n[^\S\n]*")


def strip_qq_in_at(text: str) -> str:
    """剔除 ``@昵称(QQ号)`` 中的 QQ 号，保留昵称并在其后追加一个空格。

    匹配规则：

    - 识别 ``@<昵称>(<数字>)`` 或 ``@<昵称>（<数字>）`` 整段
    - 半角 ``()`` 与全角 ``（）`` 都识别，左右括号可混搭
    - 括号内必须是 1~20 位纯数字才匹配；非数字（如 ``(笑)``）保持原样
    - 昵称为 ``@`` 后 1~32 个非空白、非括号、非 ``@`` 字符
    - 一条消息中多个 @ 全部替换
    - 替换后将连续的行内空白压成一个空格，保留换行
    - 用 ``strip()`` 裁掉首尾空白

    Args:
        text: 原始文本，可能包含 ``@昵称(QQ号)`` 片段。

    Returns:
        清洗后的文本。若输入不含可匹配片段，仅做空白规整。

    Examples:
        >>> strip_qq_in_at("@摆烂的七十七(1739244187)对呀")
        '@摆烂的七十七 对呀'
        >>> strip_qq_in_at("@xxx（10086）你好")
        '@xxx 你好'
        >>> strip_qq_in_at("@小明(笑) 这个不动")
        '@小明(笑) 这个不动'
    """
    if not text:
        return text

    # 第 1 步：把 @昵称(数字) 整段替换为 "@昵称 "（注意尾部空格）
    replaced = _AT_QQ_PATTERN.sub(lambda m: f"@{m.group(1)} ", text)

    # 第 2 步：把行内连续空白压成一个空格（保留 \n）
    compacted = _INLINE_WS_PATTERN.sub(" ", replaced)

    # 第 3 步：清掉换行符前后的空格（避免 "@张三 \n" 留下尾随空格）
    compacted = _NEWLINE_WS_PATTERN.sub("\n", compacted)

    # 第 4 步：裁掉首尾空白
    return compacted.strip()


if __name__ == "__main__":
    assert strip_qq_in_at("@摆烂的七十七(1739244187)对呀，我是河北人") == "@摆烂的七十七 对呀，我是河北人"
    assert strip_qq_in_at("@xxx（10086）你好") == "@xxx 你好"
    assert strip_qq_in_at("@a(123)@b(456)合并") == "@a @b 合并"
    assert strip_qq_in_at("普通文本不含@") == "普通文本不含@"
    assert strip_qq_in_at("@小明(笑) 这个不动") == "@小明(笑) 这个不动"
    assert strip_qq_in_at("@张三(12345)\n@李四(67890)") == "@张三\n@李四"
    assert strip_qq_in_at("订单号(12345)出货") == "订单号(12345)出货"
    assert strip_qq_in_at("") == ""
    assert strip_qq_in_at("   @abc(111)   ") == "@abc"
    assert strip_qq_in_at("@a（123)混搭") == "@a 混搭"
    assert strip_qq_in_at("@a(123）混搭") == "@a 混搭"
    print("ALL OK")
