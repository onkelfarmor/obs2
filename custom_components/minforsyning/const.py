from datetime import timedelta

DOMAIN = "minforsyning"
PLATFORMS = ["sensor"]

# KMD Easy Energy OAuth2 / OIDC
IDENTITY_BASE_URL = "https://easy-energy-identity.kmd.dk"
LOGIN_URL = f"{IDENTITY_BASE_URL}/Identity/Account/Sign/Login"
TOKEN_URL = f"{IDENTITY_BASE_URL}/oidc/token"
AUTHORIZE_PATH = "/oidc/authorize"

CLIENT_ID = "1DA5CFAF-F67F-4DA1-A1A6-513A7768F994"
REDIRECT_URI = "https://minforsyning-2.kmd.dk/login"
SCOPE = "openid profile pluginapi_int"
APP_ID = "dd944b17-c780-4e62-8b5d-ae85a2c30b9e"

# MinForsyning API
API_BASE_URL = "https://minforsyning-2.kmd.dk"

# Config entry keys
CONF_UTILITY = "utility"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN_EXPIRES = "token_expires"

DEFAULT_UTILITY = "0654000"
UPDATE_INTERVAL = timedelta(hours=1)
