from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime, Boolean
import datetime
from sqlalchemy.orm import relationship, backref
from database import Base

class Chat(Base):
    __tablename__ = 'chats'
    id = Column(Integer, primary_key=True)
    chat_id = Column(String(512), unique=True)  

    def __repr__(self):
        return '<Chat chat_id: {}>'.format(self.chat_id)
