import traceback
import re
from dataclasses import dataclass
import difflib
import logging

""" 
    Process incoming chat messages and generate route outputs.
"""

from wrapper import DelhiMetroWrapper

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
logger = logging.getLogger(__name__)

metro_wrapper = DelhiMetroWrapper()

def send_message(update, context, message: str):
    """ Send message to the chat in an update. """
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)

def process_stations_chat(update, context):
    """ Generate message for the /stations command """
    logger.info(f'{update.effective_chat.id} - requesting stations')
    
    all_stations = metro_wrapper.get_all_stations()
    msg = '\n'.join(all_stations)

    return msg

@dataclass
class RouteChatException(Exception):
    """ Invalid route chat message. """
    message: str = "Failed to route."

@dataclass
class InvalidFromStationError(Exception):
    """ Invalid from station text passed to /route. """
    message: str = "Error: Invalid from station"

@dataclass
class InvalidToStationError(Exception):
    """ Invalid To station text passed to /route """
    message: str = "Error: Invalid from station"

CLOSEST_MATCH_CUTOFF = 0.4

def process_route_chat(update, context):
    """ 
        Process messages for the route command or regular messages following <to> or <from>

        1) Remove /route
        2) All comparisons are uppercase.
        3) Extract message around the to.
    """
    try:
        chat_msg = update.message.text.replace('/route', '')
        chat_msg = chat_msg.upper()

        ROUTE_RE = re.compile(r'(?i)(?P<from>[\w\s]+).to.(?P<to>[\w\s]+)', re.IGNORECASE)

        frm_text, to_text = ROUTE_RE.search(chat_msg).group('from', 'to')
        frm_text = frm_text.strip()
        to_text = to_text.strip()

        all_stations = metro_wrapper.get_all_stations()
        from_station = difflib.get_close_matches(frm_text, all_stations, cutoff=CLOSEST_MATCH_CUTOFF)
        if len(from_station) <= 0:
            raise InvalidFromStationError()
        
        from_station = from_station[0]
            
        to_station = difflib.get_close_matches(to_text, all_stations, cutoff=CLOSEST_MATCH_CUTOFF)
        if len(to_station) <= 0:
            raise InvalidToStationError()

        to_station = to_station[0]

        logger.info(f'{update.effective_chat.id} - generate route: {from_station} -> {to_station}')
        route_msg = metro_wrapper.get_route(from_station, to_station)
        
        return route_msg
    except:
        traceback.print_exc()
        raise RouteChatException()    