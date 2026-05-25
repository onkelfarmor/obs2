DOMAIN = "navimow_baden"

OAUTH2_AUTHORIZE = "https://navimow-h5-fra.willand.com/smartHome/login?channel=homeassistant"
OAUTH2_TOKEN = "https://navimow-fra.ninebot.com/openapi/oauth/getAccessToken"
CLIENT_ID = "homeassistant"
CLIENT_SECRET = "57056e15-722e-42be-bbaa-b0cbfb208a52"

API_BASE = "https://navimow-fra.ninebot.com"

UPDATE_INTERVAL = 60

CONF_DOCK_LAT = "dock_latitude"
CONF_DOCK_LNG = "dock_longitude"

CMD_START_STOP = "action.devices.commands.StartStop"
CMD_PAUSE_UNPAUSE = "action.devices.commands.PauseUnpause"
CMD_DOCK = "action.devices.commands.Dock"

VEHICLE_STATE_MAP = {
    "idle": "docked",
    "docked": "docked",
    "charging": "docked",
    "mowing": "mowing",
    "paused": "paused",
    "returning": "docked",
    "error": "error",
    "unknown": "error",
}
