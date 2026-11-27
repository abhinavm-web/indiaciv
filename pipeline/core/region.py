"""The country this map draws, in one place.

Everything that was "the lower 48" in usaciv is read from here, so the builders do not hard-code a country.
"""

COUNTRY = "India"
COUNTRY_ISO3 = "IND"
COUNTRY_ISO2 = "IN"
CAPITAL = "Delhi"

# Albers equal-area conic fitted to India (about 6.7-37.1 N, 68-97.5 E): standard parallels at about 1/6 and 5/6 of
# the latitude span.
ALBERS = {"lat1": 12.0, "lat2": 32.0, "lat0": 22.0, "lon0": 82.0}

# lon/lat window around the country and the map margin (neighbours, the Arabian Sea, the Bay of Bengal).
BBOX = (64.0, 4.5, 100.0, 39.0)

HEX_RADIUS_KM = 20.0
MARGIN_KM = 200.0
