import os, sys
import logging
import difflib
import traceback

from dotenv import load_dotenv
load_dotenv()

import messages
from wrapper import DelhiMetroWrapper

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN') 

if TELEGRAM_TOKEN is None:
    sys.exit(1)

updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dispatcher = updater.dispatcher

def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=messages.WELCOME_TEXT)
    
def route(update, context):
    try:
        chat_msg = update.message.text.replace('/route', '')
        frm_text, to_text = chat_msg.split(' to ')
        frm_text = frm_text.upper()
        to_text = to_text.upper()

        all_stations = metro_wrapper.get_all_stations()
        from_station = difflib.get_close_matches(frm_text, all_stations)
        if len(from_station) <= 0:
            context.bot.send_message(chat_id=update.effective_chat.id, text='From station not found.\n' + messages.ROUTE_DEFAULT_TEXT)
            return
            
        from_station = from_station[0]
        print('From: ', from_station)
            
        to_station = difflib.get_close_matches(to_text, all_stations)
        if len(to_station) <= 0:
            context.bot.send_message(chat_id=update.effective_chat.id, text='To station not found.\n' + messages.ROUTE_DEFAULT_TEXT)
            return
        to_station = to_station[0]
        print('To: ', to_station)

        route_msg = metro_wrapper.get_route(from_station, to_station)

        context.bot.send_message(chat_id=update.effective_chat.id, text=route_msg)
    except:
        traceback.print_exc()
        context.bot.send_message(chat_id=update.effective_chat.id, text='Failed to handle request. \n' + messages.ROUTE_DEFAULT_TEXT)

def stations(update, context):
    all_stations = metro_wrapper.get_all_stations()
    out_msg = '\n'.join(all_stations)
    context.bot.send_message(chat_id=update.effective_chat.id, text=out_msg)

def regular(update, context):
    try:
        chat_msg = update.message.text.replace('/route', '')
        chat_msg = chat_msg.upper()
        frm_text, to_text = chat_msg.split(' TO ')
        frm_text = frm_text
        to_text = to_text

        all_stations = metro_wrapper.get_all_stations()
        from_station = difflib.get_close_matches(frm_text, all_stations, cutoff=0.4)
        if len(from_station) <= 0:
            context.bot.send_message(chat_id=update.effective_chat.id, text='From station not found.\n' + messages.ROUTE_DEFAULT_TEXT)
            return
            
        from_station = from_station[0]
        print('From: ', from_station)
            
        to_station = difflib.get_close_matches(to_text, all_stations, cutoff=0.4)
        if len(to_station) <= 0:
            context.bot.send_message(chat_id=update.effective_chat.id, text='To station not found.\n' + messages.ROUTE_DEFAULT_TEXT)
            return
        to_station = to_station[0]
        print('To: ', to_station)

        route_msg = metro_wrapper.get_route(from_station, to_station)

        context.bot.send_message(chat_id=update.effective_chat.id, text=route_msg)
    except:
        traceback.print_exc()
        context.bot.send_message(chat_id=update.effective_chat.id, text='Failed to handle request. \n' + messages.ROUTE_DEFAULT_TEXT)

start_handler = CommandHandler('start', start)
route_handler = CommandHandler('route', route)
station_handler = CommandHandler('stations', stations)
regular_handler = MessageHandler(Filters.regex(r'.(to|TO|tO|To).'), regular)

dispatcher.add_handler(start_handler)
dispatcher.add_handler(route_handler)
dispatcher.add_handler(station_handler)
dispatcher.add_handler(regular_handler)

if __name__ == '__main__':
    metro_wrapper = DelhiMetroWrapper()
    updater.start_polling()