from strenum import StrEnum


class ParserType(StrEnum):
    PRESENTATION = "presentation"
    LAWS = "laws"
    MANUAL = "manual"
    PAPER = "paper"
    BOOK = "book"
    QA = "qa"
    TABLE = "table"
    NAIVE = "naive"
    PICTURE = "picture"
    ONE = "one"
    AUDIO = "audio"
    EMAIL = "email"
    KG = "knowledge_graph"
    TAG = "tag"
