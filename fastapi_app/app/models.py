from sqlalchemy import Column, String, Integer, BigInteger, Text
from .database import Base

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, index=True, nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
