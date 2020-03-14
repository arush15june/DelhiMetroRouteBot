import scraper
import os
import logging

""" 
    Wrapper around StationScraper for rendering, cache control, updating.
"""

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
logger = logging.getLogger(__name__)


class DelhiMetroWrapper:

    STATIONS_FILE = 'stations.data'
    STATION_PERSIST_ENV = 'STATIONS_PERSIST'
    STATIONS_BEFORE_SAVE = 1

    def __init__(self):
        """ Load stations from file if file exists. """
        persistence = os.getenv(self.STATION_PERSIST_ENV)
        self.scraper = scraper.StationScraper(
            persist=persistence,
            file=self.STATIONS_FILE,
            stations_before_save=self.STATIONS_BEFORE_SAVE
        )

    def get_all_stations(self):
        """ Return list of all station names. """
        return self.scraper.stations.keys()
    
    def get_station_by_key(self, station_name: str):
        """ Get station with rendered routes by key """
        st: scraper.Station = self.scraper.stations[station_name]
        st.route = [self.get_route(rt) for rt in st.route]

        return st

    def _get_route(self, frm: str, to: str) -> scraper.Route:
        """ Return route for frm -> to. """
        route = self.scraper.get_route(self.scraper.stations[frm], self.scraper.stations[to])
        return route
    
    def _render_route(self, route: scraper.Route) -> str:
        rendered_route = f'''Route from \U0001F6A9 {route.frm.name} to \U0001F4CD {route.to.name}
\U0001F4B2 Normal Fare: \u20B9{route.fare['normal']}
\U0001F3F7 Concessional Fare: \u20B9{route.fare['concessional']}
\U0001F557 Time: {route.time} minutes
\U0001F689 Stations: {route.stations}
\U0001F38C Interchanges: {route.interchange}

'''

        for station in route.route:
            if station.name == 'INTERCHANGE':
                rendered_route += '\n\U0001F38C INTERCHANGE\n\n'
            else:
                if station.name == route.frm.name:
                    rendered_route += f'\U0001F6A9 {station.name}\n' # :triangular_flag:
                elif station.name == route.to.name:
                    rendered_route += f'\U0001F4CD {station.name}\n' # :round_pushpin:
                else:
                    rendered_route += f'\U0001F687 {station.name}\n'

        return rendered_route

    def get_route(self, frm: str, to:str) -> str:
        """ Get rendered route for frm -> to. """
        route = self._get_route(frm, to)
        return self._render_route(route)
