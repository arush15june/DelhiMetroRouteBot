from dataclasses import dataclass, field
from typing import List, Dict
import logging
import asyncio
import traceback
import pickle
import os
import copy

import requests
from bs4 import BeautifulSoup

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
logger = logging.getLogger(__name__)

""" 
    Scrape http://www.delhimetrorail.com/ for station routes, fares and timings.

    Uses the http://www.delhimetrorail.com/metro-fares.aspx endpoint.

    - Use
        - StationScraper
        Stateful metro station scraper. Extract stations, generate routes, cache routes in memory.

        - Capabilities
            - Scrape available stations on http://www.delhimetrorail.com/metro-fares.aspx
            - Generate and store route from any station in the above list to any other station on-demand.
            - Cache generated routes.
            - Ability to cache all permutations of routes using extracted station list.

    - TODO
        - Serialize to storage, sqlite, other storage/serialization formats.

    - Extended Scope
        - Add NMRC Stations.
"""

@dataclass
class Station:
    name: str
    value: int
    # Dict[str, Route]
    routes: dict = field(default_factory=dict)

INTERCHANGE = Station(name='INTERCHANGE', value=-1)

@dataclass
class Route:
    frm: Station
    to: Station
    time: int = 0 # in mins
    fare: Dict[str, int] = field(default_factory=lambda: {'normal': 0, 'concessional': 0}) # 'normal', 'concessional'
    interchange: int = 0
    stations: int = 0
    route: List[Station] = field(default_factory=list)

class StationScraper:
    """ 
        Extract metro stations and metadata, generate routes, cache routes.
    """

    DMRC_URL = 'http://www.delhimetrorail.com'
    METRO_FARE_URI = '/metro-fares.aspx'
    METRO_FARE_URL = DMRC_URL + METRO_FARE_URI

    FROM_SELECT_EL_ID = 'ctl00_MainContent_ddlFrom'

    """ All variables to extract from HTML """
    FORM_VARS_EXTRACT = [
        '__VIEWSTATE',
        '__VIEWSTATEGENERATOR',
        '__VIEWSTATEENCRYPTED',
        '__EVENTVALIDATION',
        'ctl00$headerMenu$rptProUpdate$ctl00$hdnID',
        'ctl00$headerMenu$rptProUpdate$ctl01$hdnID',
        'ctl00$headerMenu$rptProUpdate$ctl02$hdnID',
        'ctl00$headerMenu$rptProUpdate$ctl03$hdnID',
        'ctl00$headerMenu$rptProUpdate$ctl04$hdnID',
        'ctl00$headerMenu$rptProUpdate$ctl05$hdnID',
        'ctl00$MainContent$btnShowFare',
    ]

    """ Variables in form data for generating routes. """
    ROUTE_FORM_VARS = {
        'from': 'ctl00$MainContent$ddlFrom',
        'to': 'ctl00$MainContent$ddlTo'
    }

    """ Unconfirmed if setting this UA makes any difference. """
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36'

    """ Class name to extract fares from divs. """
    NORMAL_FARE_DIV_CLASS = 'fare_new_nor_right'
    CONCESSIONAL_FARE_DIV_CLASS = 'fare_new_right_right'

    """ Class name to extract stations from div. """
    STATION_LIST_DIV_CLASS = 'fr_stations'

    """ Class name to extract extra data (time, stations, interchange) from list. """
    EXTRA_DATA_DIV_CLASS = 'fr_sect1'

    """ 
        Some station names in route list result are not the same as in station
        select dropdown, this is a list of transforms for the exceptions.
    """
    STATION_NAME_EXCEPTION_TRANSFORMS = {
        'BARAKHAMBA': (lambda: 'BARAKHAMBA ROAD'),
        'JANAK PURI WEST': (lambda: 'JANAKPURI WEST'),
        'JANAK PURI EAST': (lambda: 'JANAKPURI EAST'),
        'DABRI MOR': (lambda: 'DABRI MOR JANAKPURI SOUTH'),
        'R.K.ASHRAM MARG': (lambda: 'RK ASHRAM MARG'),
        'ESI HOSPITAL': (lambda: 'ESI BASAIDARAPUR'),
        'SOUTH CAMPUS': (lambda: 'DURGABAI DESHMUKH SOUTH CAMPUS'),
        'DELHI CANTT.': (lambda: 'DELHI CANTT'),
        'SIR VISHWESHARIAH MOTI BAGH': (lambda: 'SIR VISHWESHWARAIAH MOTI BAGH'),
        'MAUJPUR-BABARPUR': (lambda: 'MAUJPUR - BABARPUR'),
        'RAJA NAHAR SINGH BALLABHGARH': (lambda: 'RAJA NAHAR SINGH - BALLABHGARH'),
        'ROHINI SECTOR 18 19': (lambda: 'ROHINI SECTOR 18,19'),
        'SHAHEED STHAL NEW BUS ADDA': (lambda: 'SHAHEED STHAL - NEW BUS ADDA'),
        'TRILOKPURI-SANJAY LAKE': (lambda: 'TRILOKPURI - SANJAY LAKE'),
    }

    def __init__(self, **kwargs):
        """ 
        Initialize scraper state,
            list of stations by name => self.stations
            list of stations by value mapping to name => self.stations_value_to_name
            route form vars => self.form_vars
        """
        logger.info("Setting up scraper, collecting information.")
        self.stations: Dict[str, Station] = dict()
        self.stations_value_to_name: Dict[int, str] = dict()

        self.form_vars = {}
        self.sess = requests.Session()
        self.sess.headers.update({
            'User-Agent': self.USER_AGENT
        })
        
        self.persist = kwargs.get('persist', False)
        self.stations_before_save = kwargs.get('stations_before_save', 1)
        self.station_fetch_count = 0

        self.stations_file = kwargs.get('file')

        if self.stations_file is not None and os.path.exists(self.stations_file):
            logger.info(f'loading from file {self.stations_file}')
            self.load_stations(self.stations_file)
        else:
            asyncio.run(self._scrape_init())

    def _serialize_stations(self):
        """ Serialize scrapers and generate bytestream. """
        return pickle.dumps(copy.deepcopy(self.stations))

    def save_stations(self, path: str, **kwargs):
        """ Serialize in-memory stations on disk. """
        if self.station_fetch_count >= self.stations_before_save or kwargs.get('force'):
            with open(path, 'wb') as f:
                pickle.dump(copy.deepcopy(self.stations), f)
            self.stations_fetch_count = 0
            
    def load_stations(self, path: str):
        """ Load serialized stations from disk. """
        with open(path, 'rb') as f:
            self.stations = pickle.load(f)
    
    def persist_stations(self, **kwargs):
        if self.persist:
            logger.info(f'saving stations to file {self.stations_file}')
            self.save_stations(self.stations_file, **kwargs)
    
    async def _scrape_init(self):
        """ 
        Scrape the website for initial .
            - Station names and values.
            - ASP.NET Form Vars
        """
        r = self.sess.get(self.METRO_FARE_URL)
        self.soup = BeautifulSoup(r.text, 'html.parser')

        soup_extractors = [
            self._extract_stations(self.soup),
            self._extract_form_vars(self.soup)
        ]

        await asyncio.gather(
            *soup_extractors
        )        

        self.persist_stations(force=True)

    async def _extract_stations(self, soup):
        """ 
            Extract all stations from the html content.
        """
        select_el = soup.find('select', id=self.FROM_SELECT_EL_ID)
        stations = [Station(name=option.text.strip().replace('\r\n', ''), value=int(option['value'])) for option in select_el if option != '\n']
        
        logger.info(f'extracted {len(stations)} stations')
        
        for station in stations:
            self.stations[station.name] = station
            self.stations_value_to_name[station.value] = station.name

    async def _extract_form_vars(self, soup):
        """
            Extract and set form vars in self.form_vars.
        """
        for var_name in self.FORM_VARS_EXTRACT:
            inp_el = soup.find('input', {'name': var_name})
            self.form_vars[var_name] = inp_el['value']

        logger.info("extracted form variables")    
        
    def generate_route_vars(self, frm: Station, to: Station):
        """  
            Generate from and to station POST payload for request to METRO_FARE_URL
        """
        return {
            self.ROUTE_FORM_VARS['from']: frm.value,
            self.ROUTE_FORM_VARS['to']: to.value
        }

    async def _extract_route_fare(self, soup, route):
        """ 
            Extract fare of a route from route page soup.
        """
        try:
            normal_fare_div = soup.find('div', {'class': self.NORMAL_FARE_DIV_CLASS})
            concessional_fare_div = soup.find('div', {'class': self.CONCESSIONAL_FARE_DIV_CLASS})
            
            normal_fare = int(normal_fare_div.text)
            concessional_fare = int(concessional_fare_div.text)
            
            route.fare['normal'] = normal_fare
            route.fare['concessional'] = concessional_fare
        except:
            traceback.print_exc()
            route.fare['normal'] = 0
            route.fare['concessional'] = 0
    
    def _resolve_station_list_ul(self, station_list_soup, route):
        """  
            Extract station list from an unordered list.

            Many times different Change Here and stations will be in nested ULs and LIs.
            This recursively creates the correct list of stations in route with interchange stations.

            1) Iterate over every element in the passed UL.
            2) If the item is a <li>
                2a) If there is a 'Change Here' in the item,
                    the station is added and an interchange is added
                2b) otherwise the station is directly added.
            3) If the item is a <ul>, recursively resolve the ul.
        """
        for item in station_list_soup: 
            if item.name == 'li':
                if item.find('b') or 'Change Here' in item.text:
                    item.b.decompose()

                    station_name = item.text.strip().upper()
                    try:    
                        station_name = self.STATION_NAME_EXCEPTION_TRANSFORMS[station_name]()
                    except:
                        pass
                    
                    try:
                        route.route.append(self.stations[station_name])
                    except:
                        traceback.print_exc()
                    route.route.append(INTERCHANGE)
                else:
                    station_name = item.text.strip().upper()
                    try:    
                        station_name = self.STATION_NAME_EXCEPTION_TRANSFORMS[station_name]()
                    except:
                        pass
                    
                    try:
                        route.route.append(self.stations[station_name])
                    except:
                        traceback.print_exc()
            elif item.name == 'ul':
                self._resolve_station_list_ul(item, route)
    
    async def _extract_route_list(self, soup, route):
        """ 
            Extract the station route list from page soup.

            Start with the first UL element containing the station list and resolve it 
            using self._resolve_station_list_ul which creates the route list.
        """
        stations_div = soup.find('div', {'class': self.STATION_LIST_DIV_CLASS})
        print(soup)
        print(stations_div)
        station_list = stations_div.find('ul')

        self._resolve_station_list_ul(station_list, route)    
    
    async def _extract_route_extra(self, soup, route):
        """ 
            Extract extra data (time, interchanges, stations) from a route.
        """
        extra_data_div = soup.find('div', {'class': self.EXTRA_DATA_DIV_CLASS})
        extra_data_list = extra_data_div.ul
        
        async def _extract_time(item, route):
            try:
                route.time = item.text.split(' - ')[1].split(' ')[0] # Timing - 53 Min
            except:
                route.time = 0
            
        async def _extract_stations(item, route):
            try:
                route.stations = item.text.split(' - ')[1] #  Stations - 26
            except:
                route.stations = 0

        async def _extract_interchange(item, route):
            try:
                route.interchange = item.text.split(' - ')[1] # Interchange - 3
            except:
                route.interchange = 0
        
        data_extractors = [
            _extract_time,
            _extract_stations,
            _extract_interchange
        ]

        running_tasks = []

        for i, (item) in enumerate(extra_data_list):
            running_tasks.push(data_extractors[i](item, route))

        await asyncio.gather(
            *running_tasks
        )
        

    async def _extract_route_info(self, soup, route):
        """ 
            Extract all info about a route from a soup.
        """
        extractors = [
            self._extract_route_fare(soup, route),
            self._extract_route_list(soup, route),
            self._extract_route_extra(soup, route),
        ]

        await asyncio.gather(
            *extractors
        )

        logger.info(f'''scraped route - {route.frm.name} {route.to.name} fare: {route.fare['normal']} {route.fare['concessional']} stations: {route.stations}''')

    async def _scrape_route(self, frm: Station, to: Station) -> Route:
        """ 
            Scrape a route from METRO_FARE_URL for Station frm to Station to.
        """
        form_data = {
            **self.form_vars,
            **self.generate_route_vars(frm, to),
        }

        r = self.sess.post(
            self.METRO_FARE_URL,
            data=form_data,
        )
        route_soup = BeautifulSoup(r.text ,'html.parser')
        route = Route(frm=frm, to=to)
        await self._extract_route_info(route_soup, route)

        return route

    async def _async_get_route(self, frm: Station, to: Station):
        """  
            Async implementation of the get route function.
        """
        if to.name in frm.routes:
            return
            
        scraped_route = await self._scrape_route(frm, to)
        self.stations[frm.name].routes[to.name] = scraped_route
        
    def get_route(self, frm: Station, to: Station):
        """  
            Blocking Wrapper for _async_get_route in sync.
        """
        if to.name not in frm.routes:
            asyncio.run(self._async_get_route(frm, to))
            self.stations_fetch_count += 1
            self.persist_stations()
        
        return frm.routes[to.name]

    async def _async_build_route_cache(self):
        """ 
            Async implementation of building the complete route cache.
        """
        running_tasks = []
        
        for frm_name, frm in self.stations.items():
            for to_name, to in self.stations.items():
                if frm_name == to_name:
                    continue
                running_tasks.append(self._async_get_route(frm, to))
                
        await asyncio.gather(
            *running_tasks
        )

    def build_route_cache(self):
        """ Blocking wrapper for _async_build_route_cache """
        asyncio.run(self._async_build_route_cache())

    async def _async_build_station_route_cache(self, station):
        """ 
            Async implementation to build the route cache for a particular station.
        """
        running_tasks = []
        
        for to_name, to in self.stations.items():
                if station.name == to_name:
                    continue
                running_tasks.append(self._async_get_route(station, to))
                
        await asyncio.gather(
            *running_tasks
        )
        
    def build_station_route_cache(self, station):
        """ Blocking wrapper for _async_build_station_route_cache to build a particular station's route cache. """
        asyncio.run(self._async_build_station_route_cache(station))


if __name__ == "__main__":
    logger.info('STARTING')
    scraper = StationScraper()

    print(' '.join(scraper.stations))
    scraper.build_station_route_cache(scraper.stations['YAMUNA BANK'])