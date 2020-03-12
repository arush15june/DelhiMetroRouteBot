import scraper

""" 
    Wrapper around StationScraper for rendering, cache control, updating.
"""

class DelhiMetroWrapper:

    def __init__(self):
        self.scraper = scraper.StationScraper()

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
        return self.scraper.get_route(self.scraper.stations[frm], self.scraper.stations[to])
    
    def _render_route(self, route: scraper.Route) -> str:
        rendered_route = f'''Route from {route.frm.name} to {route.to.name}
Normal Fare: \u20B9{route.fare['normal']}
Concessional Fare: \u20B9{route.fare['concessional']}
Time: {route.time} minutes
Stations: {route.stations}
Interchanges: {route.interchange}

'''

        for station in route.route:
            if station.name == 'INTERCHANGE':
                rendered_route += '\n'
                rendered_route += 'INTERCHANGE'
                rendered_route += '\n\n'
            else:
                rendered_route += station.name + '\n'

        return rendered_route

    def get_route(self, frm: str, to:str) -> str:
        """ Get rendered route for frm -> to. """
        route = self._get_route(frm, to)
        return self._render_route(route)
