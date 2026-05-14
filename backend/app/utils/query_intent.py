import re
from enum import StrEnum


class QueryIntent(StrEnum):
    CODEBASE = "codebase"
    CHITCHAT = "chitchat"
    MEMORY = "memory"
    GENERAL = "general"


CHITCHAT_PATTERNS = (
    r"^(你好|您好|hi|hello|hey|哈喽|嗨)[!！。.\s]*$",
    r"^(谢谢|感谢|thanks|thank you)[!！。.\s]*$",
    r"^(再见|拜拜|bye)[!！。.\s]*$",
    r"^(你是谁|你能做什么|你可以做什么|介绍一下你自己)[?？!！。.\s]*$",
)

MEMORY_PATTERNS = (
    r"(上一个|上一条|刚才|之前|前面).*(问题|问了什么|说了什么|聊了什么)",
    r"(最开始|一开始|开始|第一个|第一条).*(问题|问了什么|说了什么)",
    r"(我|用户).*(问过|问了).*(什么|哪些)",
    r"(你还记得|还记得).*(吗|什么|哪些|我)",
    r"(总结|概括|回顾).*(对话|聊天|问题|本轮|刚才)",
    r"(我们|咱们).*(聊到哪里|聊了什么|说到哪)",
)

CODEBASE_KEYWORDS = (
    "代码",
    "代码库",
    "仓库",
    "项目",
    "文件",
    "目录",
    "模块",
    "函数",
    "方法",
    "类",
    "接口",
    "调用",
    "实现",
    "入口",
    "配置",
    "依赖",
    "报错",
    "异常",
    "日志",
    "数据库",
    "路由",
    "组件",
    "变量",
    "参数",
    "返回",
    "测试",
    "部署",
    "启动",
    "在哪里",
    "在哪",
    "怎么运行",
    "怎么启动",
    "怎么实现",
    "调用链",
    "数据流",
)

CODEBASE_PATTERNS = (
    r"[A-Za-z0-9_./-]+\.(py|js|jsx|ts|tsx|java|go|rs|c|cpp|h|hpp|md|json|ya?ml|toml|ini|sql)",
    r"\b[A-Za-z_][A-Za-z0-9_]*(Service|Controller|Router|Model|Schema|Config|Client|Manager|Repository|Store|Hook|Provider)\b",
    r"\b(GET|POST|PUT|DELETE|PATCH)\s+/",
    r"/[A-Za-z0-9_./{}:-]+",
)


def classify_query_intent(query: str | None) -> QueryIntent:
    text = (query or "").strip()
    if not text:
        return QueryIntent.CHITCHAT

    lowered = text.lower()
    for pattern in CHITCHAT_PATTERNS:
        if re.match(pattern, lowered, flags=re.IGNORECASE):
            return QueryIntent.CHITCHAT

    for pattern in MEMORY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return QueryIntent.MEMORY

    if any(keyword in text for keyword in CODEBASE_KEYWORDS):
        return QueryIntent.CODEBASE

    for pattern in CODEBASE_PATTERNS:
        if re.search(pattern, text):
            return QueryIntent.CODEBASE

    return QueryIntent.GENERAL


def chitchat_answer(query: str | None) -> str:
    text = (query or "").strip()
    if re.match(r"^(你是谁|你能做什么|你可以做什么|介绍一下你自己)", text):
        return (
            "我是智码小源，一个代码库问答助手。你可以先上传或选择代码仓库，然后问我某个功能在哪里实现、"
            "接口调用链是什么、配置从哪里读取、某个报错可能来自哪段代码等问题。"
        )
    if re.match(r"^(谢谢|感谢|thanks|thank you)", text, flags=re.IGNORECASE):
        return "不客气。你可以继续问我当前代码库里的实现、调用链、配置或模块职责。"
    if re.match(r"^(再见|拜拜|bye)", text, flags=re.IGNORECASE):
        return "再见，后续需要查代码库时随时回来。"
    return "你好，我是智码小源。你可以问我当前代码库里的实现位置、调用链、配置来源、模块职责或报错定位。"
