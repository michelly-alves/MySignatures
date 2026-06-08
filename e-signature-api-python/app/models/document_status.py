from sqlalchemy import Column, Integer, String
from app.db.base import Base

class DocumentStatus(Base):
    __tablename__ = "document_status"

    status_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)