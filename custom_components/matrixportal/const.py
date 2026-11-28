"""Constants of the MatrixPortal integration."""

DOMAIN = "matrixportal"

# The display listens here for the integration (config.h, LINK_PORT).
LINK_PORT = 81
# Messages between HA and display, see PROTOCOL.md. The display sends its version in the hello.
PROTOCOL = 1

STORAGE_KEY = f"{DOMAIN}.devices"
STORAGE_VERSION = 1

PANEL_URL_PATH = DOMAIN
PANEL_COMPONENT = "matrixportal-panel"
STATIC_URL = f"/{DOMAIN}_static"

CONF_LINK_KEY = "link_key"
CONF_PAIR_PASSWORD = "pair_password"

# Attributes the display uses. Everything else stays in HA.
FORWARDED_ATTRIBUTES = ("unit_of_measurement", "current_temperature", "hvac_action", "temperature")

# Runtime settings of the display (entities, "set" message), same names as in the firmware.
DESIGNS = ("klassisch", "kompakt", "fokus")
HEADER_MODES = ("datum", "entities", "wechselnd")
# LED strip at A2 (config.h STRIP_MAX)
STRIP_MAX = 300
# Doorbell: waves full screen, blinking frame over the display, or a short bright flash
DOORBELL_STYLES = ("wellen", "rahmen", "blitz")
STRIP_ORDERS = ("rgb", "grb", "brg", "rbg", "gbr", "bgr")
VIEWS = ("dashboard", "effekt", "effekt_tage", "effekt_laufband", "effekt_liste")
EFFECTS = (
    "plasma",
    "feuer",
    "regen",
    "sterne",
    "polarlicht",
    "lava",
    "leben",
    "ozean",
    "glut",
    "gluehwuermchen",
    "schnee",
    "feuerwerk",
    "tunnel",
    "regenbogen",
    "kaleidoskop",
    "aquarium",
    "lavalampe",
    "baelle",
    "sanduhr",
    "gewitter",
    "labyrinth",
    "wetter",
    "solar",
    "wechselnd",
)
SAVER_MODES = ("aus", "zeitfenster", "keine_termine", "beides")
COMMANDS = ("restart", "pacman", "week", "week_off", "identify", "refresh", "doorbell", "doorbell_off")

PASSWORD_LENGTH = 16

# Limits of the firmware (state.h): a longer value is refused there.
MAX_ENTITY = 63
MAX_CALENDARS = 159  # joined with ","
MAX_LABEL = 7
MAX_INFO = 4
MAX_BLOCKERS = 63
MAX_TZ = 63
# A calendar message must fit the WebSocket buffer of the display (WEBSOCKETS_MAX_DATA_SIZE 24 KiB).
MAX_CALENDAR_BYTES = 18000
MAX_EVENTS = 80

DEFAULT_CONFIG = {
    "solar": "",
    "office": "",
    "room": "",
    "weather": "",
    "calendars": [],
    "work_calendar": "",
    "info": [],
    "blockers": "Blocker,Block,Fokus,Focus",
    "tz": "",
    "solar_max": 800,
    "office_max": 400,
}

SIGNAL_UPDATED = f"{DOMAIN}_updated_{{}}"
