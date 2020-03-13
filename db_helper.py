import logging

from database import init_db, db_session
from models import Chat

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
logger = logging.getLogger(__name__)

def init():
    """ Initialize database """
    logger.info("Initializing database.")
    init_db()

def insert_chat_id(chat_id):
    """ Add chat_id to the database of chats. """
    if not is_returning_chat(chat_id):
        chat = Chat(chat_id=chat_id)
        db_session.add(chat)
        db_session.commit()
        logger.info(f'Inserted new chat_id: {chat_id}. Total Chats: {get_chats()}')

        return True
        
    return False

def is_returning_chat(chat_id):
    """ Check if the chat_id is already present in the database. """
    return db_session.query(Chat.query.filter(Chat.chat_id == chat_id).exists()).scalar()

def get_chats():
    return Chat.query.count()