"""Constants for the CatGenie integration."""

from __future__ import annotations

from enum import IntEnum

DOMAIN = "catgenie"
MANUFACTURER = "Petnovations"

DEFAULT_BASE_URL = "https://iot.petnovations.com"
DEFAULT_SCAN_INTERVAL = 30  # seconds
FAST_SCAN_INTERVAL = 10  # used while a cycle is running

CONF_PHONE = "phone"
CONF_COUNTRY_CODE = "country_code"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_SIGNING_SECRET = "signing_secret"
CONF_BASE_URL = "base_url"
CONF_SCAN_INTERVAL = "scan_interval"


class CleaningState(IntEnum):
    """CLEANING_STATE_VALUES from the app (operation 'state' field)."""

    IDLE = 0
    PLAY = 1
    SUSPENDED = 2
    RESUMED = 3
    ABORT = 4
    PLAY_SPECIAL = 129


STATE_NAMES = {
    CleaningState.IDLE: "idle",
    CleaningState.PLAY: "cleaning",
    CleaningState.SUSPENDED: "paused",
    CleaningState.RESUMED: "cleaning",
    CleaningState.ABORT: "cancelled",
    CleaningState.PLAY_SPECIAL: "special_cleaning",
}

# operationStatus.progress uses 0xFF to mean "no cycle running"
PROGRESS_NONE = 255

# configuration.mode (with configuration.manual as an override)
MODE_CAT_ACTIVATION = "cat_activation"
MODE_TIME_ACTIVATION = "time_activation"
MODE_MANUAL = "manual"

# Ranges from the app's settings screens
VOLUME_MIN, VOLUME_MAX = 1, 7
CAT_DELAY_MIN_S, CAT_DELAY_MAX_S = 300, 1800
AUTO_LOCK_STEP_MIN, AUTO_LOCK_MAX_STEPS = 5, 6  # 0 (off) .. 30 min, in 5 min steps; stored in seconds
MAX_SCHEDULE_ENTRIES = 8
LOW_WASHES_LEFT = 30  # app: LOW_CLEANING_LEFT

DEVICE_TYPE_GENIE = 0

PLATFORMS = ["binary_sensor", "button", "number", "select", "sensor", "switch"]
