import re
from dataclasses import dataclass, field
from enum import StrEnum


class QueryIntent(StrEnum):
    CODEBASE = "codebase"
    CHITCHAT = "chitchat"
    MEMORY = "memory"
    GENERAL = "general"


@dataclass
class IntentResult:
    intent: QueryIntent
    confidence: float
    signals: list[str] = field(default_factory=list)
    secondary: list[QueryIntent] = field(default_factory=list)
    needs_repository: bool = False
    needs_memory: bool = False
    needs_web: bool = False


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
    "源码",
    "源代码",
    "业务逻辑",
    "初始化",
    "中间件",
    "序列化",
    "反序列化",
    "权限",
    "鉴权",
    "认证",
    "缓存",
    "队列",
    "任务",
    "模型",
    "训练",
    "推理",
    "损失函数",
    "优化器",
    "数据集",
    "checkpoint",
    "ckpt",
    "权重",
    "脚本",
    "命令",
    "参数",
    "import",
    "class",
    "function",
    "method",
    "where",
    "implemented",
    "implementation",
    "called",
    "call chain",
    "entrypoint",
    "entry point",
    "route",
    "config",
    "error",
    "exception",
    "traceback",
    "stack trace",
    "dependency",
)

CODEBASE_PATTERNS = (
    r"[A-Za-z0-9_./-]+\.(py|js|jsx|ts|tsx|java|go|rs|c|cpp|h|hpp|md|json|ya?ml|toml|ini|sql)",
    r"\b[A-Za-z_][A-Za-z0-9_]*(Service|Controller|Router|Model|Schema|Config|Client|Manager|Repository|Store|Hook|Provider)\b",
    r"\b(GET|POST|PUT|DELETE|PATCH)\s+/",
    r"/[A-Za-z0-9_./{}:-]+",
    r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*\b",
    r"\b[A-Za-z_][A-Za-z0-9_]*\([^)]*\)",
    r"\b[a-z]+(?:_[a-z0-9]+){1,}\b",
    r"\b[A-Z][A-Za-z0-9]+(?:[A-Z][A-Za-z0-9]+)+\b",
)

GENERAL_TECH_KEYWORDS = (
    "什么是",
    "是什么",
    "概念",
    "原理",
    "区别",
    "优缺点",
    "最佳实践",
    "为什么",
    "如何理解",
    "explain",
    "what is",
    "why",
    "difference",
    "best practice",
)

WEB_HINT_KEYWORDS = (
    "最新",
    "官方",
    "文档",
    "资料",
    "网上",
    "联网",
    "搜索",
    "latest",
    "official",
    "docs",
    "documentation",
)


def _append_signal(signals: list[str], signal: str):
    if signal not in signals:
        signals.append(signal)


def _clamp_confidence(score: float) -> float:
    return max(0.0, min(score, 0.99))


def classify_query_intent_detail(query: str | None) -> IntentResult:
    text = (query or "").strip()
    if not text:
        return IntentResult(
            intent=QueryIntent.CHITCHAT,
            confidence=0.95,
            signals=["empty_input"],
        )

    lowered = text.lower()
    for pattern in CHITCHAT_PATTERNS:
        if re.match(pattern, lowered, flags=re.IGNORECASE):
            return IntentResult(
                intent=QueryIntent.CHITCHAT,
                confidence=0.98,
                signals=[f"chitchat_pattern:{pattern}"],
            )

    signals: list[str] = []
    code_score = 0.0
    memory_score = 0.0
    general_score = 0.0

    for pattern in MEMORY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            memory_score += 0.85
            _append_signal(signals, f"memory_pattern:{pattern}")

    for keyword in CODEBASE_KEYWORDS:
        if keyword in text or keyword in lowered:
            code_score += 0.18
            _append_signal(signals, f"code_keyword:{keyword}")

    for pattern in CODEBASE_PATTERNS:
        if re.search(pattern, text):
            code_score += 0.35
            _append_signal(signals, f"code_pattern:{pattern}")

    for keyword in GENERAL_TECH_KEYWORDS:
        if keyword in text or keyword in lowered:
            general_score += 0.22
            _append_signal(signals, f"general_keyword:{keyword}")

    needs_web = any(keyword in text or keyword in lowered for keyword in WEB_HINT_KEYWORDS)
    if needs_web:
        _append_signal(signals, "web_hint")

    # Phrases that point a general concept back to the selected repository.
    repository_anchors = ("这个项目", "本项目", "当前项目", "这个仓库", "本仓库", "代码里", "项目中", "仓库中")
    if any(anchor in text for anchor in repository_anchors):
        code_score += 0.4
        _append_signal(signals, "repository_anchor")

    # Memory questions can also contain repository words. Keep explicit memory asks routed to memory.
    if memory_score >= 0.8 and code_score < 0.7:
        return IntentResult(
            intent=QueryIntent.MEMORY,
            confidence=_clamp_confidence(memory_score),
            signals=signals,
            needs_memory=True,
        )

    secondary: list[QueryIntent] = []
    if code_score >= 0.35:
        if general_score >= 0.22:
            secondary.append(QueryIntent.GENERAL)
        if memory_score >= 0.5:
            secondary.append(QueryIntent.MEMORY)
        return IntentResult(
            intent=QueryIntent.CODEBASE,
            confidence=_clamp_confidence(0.55 + code_score * 0.35),
            signals=signals,
            secondary=secondary,
            needs_repository=True,
            needs_memory=QueryIntent.MEMORY in secondary,
            needs_web=needs_web,
        )

    if memory_score >= 0.5:
        return IntentResult(
            intent=QueryIntent.MEMORY,
            confidence=_clamp_confidence(memory_score),
            signals=signals,
            needs_memory=True,
            needs_web=needs_web,
        )

    return IntentResult(
        intent=QueryIntent.GENERAL,
        confidence=_clamp_confidence(0.55 + general_score * 0.3),
        signals=signals or ["default_general"],
        needs_web=needs_web,
    )


def classify_query_intent(query: str | None) -> QueryIntent:
    return classify_query_intent_detail(query).intent


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
