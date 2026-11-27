"""The game-concept → real-data mapping for India, in one place.

Each yield is defined once here and exported to the browser (nation.json), so the UI and the Almanac describe exactly
what was computed. Every yield is a published count or a mapped quantity; where an area has no published figure
(district and city GDP, for example) the value is null and shown as "Pending", never estimated.
"""

from __future__ import annotations

from ..core.region import HEX_RADIUS_KM

HEX_AREA_KM2 = 3 * 3 ** 0.5 / 2 * HEX_RADIUS_KM ** 2  # pointy-top hex

YIELDS = [
    {
        "key": "food",
        "source": "Census of India 2011, Primary Census Abstract",
        "icon": "y-food",
        "emoji": "🌾",
        "label": "Food",
        "color": "#7fbf3f",
        "unit": "farm workers",
        "industries": [],
        "description": "People working on the land at the 2011 census: cultivators plus agricultural labourers, main "
        "and marginal workers (Primary Census Abstract). States and districts sum their 2011 sub-districts; a "
        "city counts its own urban agglomeration or town.",
    },
    {
        "key": "production",
        "source": "WRI Global Power Plant Database v1.3 (2021)",
        "icon": "y-production",
        "emoji": "⚙️",
        "label": "Production",
        "color": "#d9823b",
        "unit": "MW",
        "industries": [],
        "description": "Power-plant capacity in megawatts located in the area (WRI Global Power Plant Database, last "
        "updated 2021; plants built since are missing). Nuclear plants are left out of this map. A city counts "
        "the plants in its own hexes.",
    },
    {
        "key": "gold",
        "source": "RBI Handbook of Statistics on Indian States (NSO / MoSPI)",
        "icon": "y-gold",
        "emoji": "💰",
        "label": "Gold",
        "color": "#f2c94c",
        "unit": "inr",
        "industries": [],
        "description": "Gross State Domestic Product at current prices, 2022-23, in rupees (NSO state accounts, base "
        "2011-12, as published in the RBI handbook). India publishes no comparable district or city GDP series, "
        "so district and city Gold is Pending rather than estimated. States without a 2022-23 figure are Pending.",
    },
    {
        "key": "science",
        "source": "Wikidata (queried at build)",
        "icon": "y-science",
        "emoji": "🔬",
        "label": "Science",
        "color": "#4fa3e0",
        "unit": "universities",
        "industries": [],
        "description": "Universities with a Wikipedia article in at least 8 languages (Wikidata), counted where their "
        "main campus is. A rough signal of research prominence, not a measure of output.",
    },
    {
        "key": "culture",
        "source": "UNESCO World Heritage List via Wikidata (queried at build)",
        "icon": "y-culture",
        "emoji": "🎭",
        "label": "Culture",
        "color": "#b07ce0",
        "unit": "sites",
        "industries": [],
        "description": "UNESCO World Heritage properties (Wikidata), counted where they are. Parts of one property "
        "inscribed the same year and within 40 km of each other count once.",
    },
]
YIELD_KEYS = [y["key"] for y in YIELDS]
