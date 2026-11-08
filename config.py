"""Application configuration.

Every value is read from the environment (loaded from the .env file), so no
password, secret key or API token is ever written inside the source code.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _required(name):
    """Read a setting that the application cannot run without."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required setting '{name}'. "
            "Copy .env.example to .env and fill in your values."
        )
    return value


def _boolean(name, default=False):
    """Read a conventional true/false environment flag."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# --- Flask ---
SECRET_KEY = _required("SECRET_KEY")
SESSION_COOKIE_SECURE = _boolean("SESSION_COOKIE_SECURE", False)

# --- MySQL ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "service_expert")

# --- Galli Maps ---
# The map SDK runs in the browser, so this token necessarily reaches the client.
# It is still kept in .env so it can be rotated without editing source code, and
# server-side calls (reverse geocoding) use it without exposing it in page URLs.
GALLI_ACCESS_TOKEN = os.getenv("GALLI_ACCESS_TOKEN", "")

# --- Khalti payment gateway ---
# The secret key is read here and used only in server-to-server requests. It is
# never passed to a template, so it can never appear in HTML or JavaScript.
KHALTI_SECRET_KEY = os.getenv("KHALTI_SECRET_KEY", "")
KHALTI_BASE_URL = os.getenv("KHALTI_BASE_URL", "https://dev.khalti.com/api/v2/").rstrip("/")

# Khalti rejects anything under Rs 10 in production.
MINIMUM_PAYMENT_RUPEES = 10

# --- Email and password recovery ---
# RESET_BASE_URL is deliberately configured rather than copied from the Host
# header of an incoming request. That prevents a forged Host header from being
# placed into a password-reset email.
RESET_BASE_URL = os.getenv("RESET_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
RESET_TOKEN_TTL_MINUTES = int(os.getenv("RESET_TOKEN_TTL_MINUTES", "30"))
MAIL_SERVER = os.getenv("MAIL_SERVER", "")
MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
MAIL_FROM = os.getenv("MAIL_FROM", MAIL_USERNAME)
MAIL_USE_TLS = _boolean("MAIL_USE_TLS", True)
MAIL_USE_SSL = _boolean("MAIL_USE_SSL", False)

# --- Sample data ---
SEED_PASSWORD = os.getenv("SEED_PASSWORD", "Demo@1234")

# --- Map defaults (Kathmandu valley) ---
DEFAULT_MAP_CENTER_LAT = 27.7047
DEFAULT_MAP_CENTER_LNG = 85.3140

# The routing graph only covers the Kathmandu valley, so locations are rejected
# outside this box instead of silently producing a meaningless route.
VALLEY_BOUNDS = {
    "min_lat": 27.60,
    "max_lat": 27.82,
    "min_lng": 85.20,
    "max_lng": 85.52,
}
