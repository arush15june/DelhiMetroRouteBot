from dataclasses import dataclass, field
from typing import List, Dict
import logging
import asyncio

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
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

    # Variables in form data for generating routes.
    ROUTE_FORM_VARS = {
        'from': 'ctl00$MainContent$ddlFrom',
        'to': 'ctl00$MainContent$ddlTo'
    }

    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36'

    NORMAL_FARE_DIV_CLASS = 'fare_new_nor_right'
    CONCESSIONAL_FARE_DIV_CLASS = 'fare_new_right_right'

    STATION_LIST_DIV_CLASS = 'fr_stations'

    EXTRA_DATA_DIV_CLASS = 'fr_sect1'

    def __init__(self):
        """ 
        Initialize scraper state,
            list of stations by name => self.stations
            list of stations by value mapping to name => self.stations_value_to_name
            route form vars => self.form_vars
        """
        self.stations: Dict[str, Station] = dict()
        self.stations_value_to_name: Dict[int, str] = dict()

        self.form_vars = {}
        self.sess = requests.Session()
        self.sess.headers.update({
            'User-Agent': self.USER_AGENT
        })
        asyncio.run(self._scrape_init())

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

    async def _extract_stations(self, soup):
        """ 
            Extract all stations from the html content.
        """
        select_el = soup.find('select', id=self.FROM_SELECT_EL_ID)
        stations = [Station(name=option.text.rstrip().strip(), value=int(option['value'])) for option in select_el if option != '\n']
        
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

    def generate_route_vars(self, frm: Station, to: Station):
        return {
            self.ROUTE_FORM_VARS['from']: frm.value,
            self.ROUTE_FORM_VARS['to']: to.value
        }

    async def _extract_route_fare(self, soup, route):
        normal_fare_div = soup.find('div', {'class': self.NORMAL_FARE_DIV_CLASS})
        concessional_fare_div = soup.find('div', {'class': self.CONCESSIONAL_FARE_DIV_CLASS})
        
        normal_fare = int(normal_fare_div.text)
        concessional_fare = int(concessional_fare_div.text)
        
        route.fare['normal'] = normal_fare
        route.fare['concessional'] = concessional_fare
    
    def resolve_station_list_ul(self, station_list_soup, route):
        for item in station_list_soup:
            if item.name == 'li':
                if item.find('b') or 'Change Here' in item.text:
                    item.b.decompose()
                    route.route.append(self.stations[item.text.rstrip().upper()])
                    route.route.append(INTERCHANGE)
                else:
                    route.route.append(self.stations[item.text.rstrip().upper()])
            elif item.name == 'ul':
                self.resolve_station_list_ul(item, route)
    
    async def _extract_route_list(self, soup, route):
        stations_div = soup.find('div', {'class': self.STATION_LIST_DIV_CLASS})
        station_list = stations_div.find('ul')

        self.resolve_station_list_ul(station_list, route)    
    
    async def _extract_route_extra(self, soup, route):
        extra_data_div = soup.find('div', {'class': self.EXTRA_DATA_DIV_CLASS})
        extra_data_list = extra_data_div.ul
        
        def _extract_time(item, route):
            route.time = item.text.split(' - ')[1].split(' ')[0] # Timing - 53 Min
            
        def _extract_stations(item, route):
            route.stations = item.text.split(' - ')[1] #  Stations - 26

        def _extract_interchange(item, route):
            route.interchange = item.text.split(' - ')[1] # Interchange - 3
        
        data_extractors = [
            _extract_time,
            _extract_stations,
            _extract_interchange
        ]

        for i, (item) in enumerate(extra_data_list):
            data_extractors[i](item, route)

    async def _extract_route_info(self, soup, route):
        extractors = [
            self._extract_route_fare(soup, route),
            self._extract_route_list(soup, route),
            self._extract_route_extra(soup, route),
        ]

        await asyncio.gather(
            *extractors
        )

    async def _scrape_route(self, frm: Station, to: Station) -> Route:
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
        
        if to.name in frm.routes:
            return
            
        logger.info('Scraping ' + frm.name + ' -> ' + to.name)
        scraped_route = await self._scrape_route(frm, to)
        self.stations[frm.name].routes[to.name] = scraped_route
        
    def get_route(self, frm: Station, to: Station):
        if to.name not in frm.routes:
            asyncio.run(self._async_get_route(frm, to))
        
        return frm.routes[to.name]

    async def _async_build_route_cache(self):
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
        asyncio.run(self._async_build_route_cache())

    async def _async_build_station_route_cache(self, station):
        running_tasks = []
        
        for to_name, to in self.stations.items():
                if station.name == to_name:
                    continue
                running_tasks.append(self._async_get_route(station, to))
                
        await asyncio.gather(
            *running_tasks
        )
        
    def build_station_route_cache(self, station):
        asyncio.run(self._async_build_station_route_cache())


if __name__ == "__main__":
    logger.info('STARTING')
    scraper = StationScraper()
    yb = scraper.stations['YAMUNA BANK']
    ito = scraper.stations['ITO']
    scraper.build_route_cache()