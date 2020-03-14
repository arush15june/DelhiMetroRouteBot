import os, sys
import logging
import difflib
import traceback

from dotenv import load_dotenv
load_dotenv()

import messages
from wrapper import DelhiMetroWrapper
import processor
import db_helper

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN') 

if TELEGRAM_TOKEN is None:
    sys.exit(1)

""" Setup bot parameters """
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dispatcher = updater.dispatcher

def start(update, context):
    db_helper.insert_chat_id(update.effective_chat.id)
    processor.send_message(update, context, messages.WELCOME_TEXT)
    
def route(update, context):
    """ 
        Handles any incoming route commands
        /route <Source> to <Destination>
    """
    db_helper.insert_chat_id(update.effective_chat.id)
    try:
        route_message = processor.process_route_chat(update, context)
        processor.send_message(update, context, route_message)
    except processor.RouteChatException as e:
        traceback.print_exc()
        processor.send_message(update, context, f'{e.message} \n {messages.ROUTE_DEFAULT_TEXT}')

def stations(update, context):
    """ 
        Handles route commands.
        /stations or stations

        Returns a list of all stations.
    """
    db_helper.insert_chat_id(update.effective_chat.id)
    message = processor.process_stations_chat(update, context)
    processor.send_message(update, context, message)

start_handler = CommandHandler('start', start)
route_handler = CommandHandler('route', route)
station_handler = CommandHandler('stations', stations)
regular_handler = MessageHandler(Filters.regex(r'(?i).to.'), route)
regular_stations_handler = MessageHandler(Filters.regex(r'^(?i)stations'), stations)

dispatcher.add_handler(start_handler)
dispatcher.add_handler(route_handler)
dispatcher.add_handler(station_handler)
dispatcher.add_handler(regular_handler)
dispatcher.add_handler(regular_stations_handler)

if __name__ == '__main__':
    db_helper.init()
    updater.start_polling()