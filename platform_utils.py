from typing import Any


def get_platform_client(context, event) -> Any | None:
    try:
        from astrbot.api.platform import PlatformAdapterType
        platform = context.get_platform(PlatformAdapterType.AIOCQHTTP)
        if platform:
            client = platform.get_client()
            if client:
                return client
    except Exception:
        pass
    for attr_name in ("client", "_client", "bot", "_bot", "platform"):
        client = getattr(event, attr_name, None)
        if client is not None:
            return client
    return None
