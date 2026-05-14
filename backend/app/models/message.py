from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from models.base import Base

class Message(Base):
    __tablename__ = "messages"

    message_id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    session_id = Column(String(16), nullable=False)
    user_question = Column(Text, nullable=False)
    model_answer = Column(Text, nullable=False)
    create_time = Column(TIMESTAMP, server_default=func.now())
    retrieval_content = Column(Text)

class KnowledgeBase(Base):
    __tablename__ = 'knowledgebases'  # 表名
    
    id = Column(Integer, primary_key=True, autoincrement=True)  # 主键
    user_id = Column(String(255), nullable=False)  # 用户 ID
    file_name = Column(String(255), nullable=False)  # 文件名称
    created_at = Column(TIMESTAMP, nullable=False, server_default='CURRENT_TIMESTAMP')  # 创建时间
    updated_at = Column(TIMESTAMP, nullable=False, server_default='CURRENT_TIMESTAMP')  # 更新时间


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    type = Column(String(32), nullable=False, server_default="doc")
    status = Column(String(32), nullable=False, server_default="ready")
    index_name = Column(String(255), nullable=False)
    storage_path = Column(Text, nullable=False)
    root_path = Column(Text)
    archive_path = Column(Text)
    file_count = Column(Integer, nullable=False, server_default="0")
    indexed_chunks = Column(Integer, nullable=False, server_default="0")
    language_stats = Column(Text)
    metadata_json = Column(Text)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())


class SessionRepositoryContext(Base):
    __tablename__ = "session_repository_contexts"

    session_id = Column(String(16), primary_key=True)
    user_id = Column(String(255), nullable=False)
    repository_id = Column(String(64), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())

