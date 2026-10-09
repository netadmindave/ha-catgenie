"""Typed view over the 'thing' JSON returned by device/device/v2.

Field names are confirmed against a real CatGenie A.I. (fw 100.4.14R) response.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any

from .const import (
    LOW_WASHES_LEFT,
    MODE_CAT_ACTIVATION,
    MODE_MANUAL,
    MODE_TIME_ACTIVATION,
    PROGRESS_NONE,
    STATE_NAMES,
    CleaningState,
)


def parse_timestamp(value: Any) -> datetime | None:
    """Epoch s/ms or ISO-8601. Naive ISO strings from the cloud are UTC."""
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e11:  # milliseconds
            ts /= 1000
        return datetime.fromtimestamp(ts, UTC)
    if isinstance(value, str):
        try:
            if value.isdigit():
                return parse_timestamp(int(value))
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def utc_hms_to_local(value: str, tz) -> str:
    """'HH:mm:ss' UTC (as stored by the cloud) -> 'HH:MM' local."""
    h, m, *rest = (int(p) for p in value.split(":"))
    dt = datetime.combine(datetime.now(UTC).date(), time(h, m, rest[0] if rest else 0), UTC)
    return dt.astimezone(tz).strftime("%H:%M")


def local_hm_to_utc(value: str | time, tz) -> str:
    """'HH:MM[:SS]' local -> 'HH:mm:ss' UTC, like the app's localTimeToUtcTime."""
    if isinstance(value, time):
        t = value
    else:
        parts = [int(p) for p in str(value).split(":")]
        t = time(parts[0], parts[1] if len(parts) > 1 else 0, parts[2] if len(parts) > 2 else 0)
    local_dt = datetime.combine(datetime.now(tz).date(), t).replace(tzinfo=tz)
    return local_dt.astimezone(UTC).strftime("%H:%M:%S")


def format_mac(value: str | None) -> str | None:
    """'FC0FE79F4926' -> 'fc:0f:e7:9f:49:26'."""
    if not value:
        return None
    hexdigits = "".join(c for c in value if c.isalnum()).lower()
    if len(hexdigits) != 12:
        return value.lower()
    return ":".join(hexdigits[i : i + 2] for i in range(0, 12, 2))


@dataclass
class CatGenie:
    """One CatGenie unit."""

    raw: dict[str, Any]

    # identity ---------------------------------------------------------------
    @property
    def manufacturer_id(self) -> str:
        return str(self.raw.get("manufacturerId"))

    @property
    def name(self) -> str:
        return (self.raw.get("name") or "").strip() or "CatGenie"

    @property
    def mac(self) -> str | None:
        return format_mac(self.raw.get("macAddress"))

    @property
    def firmware(self) -> str | None:
        return self.raw.get("fwVersion")

    @property
    def hw_revision(self) -> str | None:
        return self.raw.get("hwRevision")

    @property
    def model(self) -> str:
        level = self.raw.get("serviceLevel")
        return f"CatGenie A.I. ({level})" if level else "CatGenie A.I."

    # status -----------------------------------------------------------------
    @property
    def configuration(self) -> dict[str, Any]:
        """A deep copy, safe to modify and send back as a full configuration."""
        cfg = self.raw.get("configuration")
        return copy.deepcopy(cfg) if isinstance(cfg, dict) else {}

    @property
    def _cfg(self) -> dict[str, Any]:
        cfg = self.raw.get("configuration")
        return cfg if isinstance(cfg, dict) else {}

    @property
    def operation(self) -> dict[str, Any]:
        op = self.raw.get("operationStatus")
        return op if isinstance(op, dict) else {}

    @property
    def state_code(self) -> int | None:
        val = self.operation.get("state")
        try:
            return int(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def state(self) -> str | None:
        code = self.state_code
        if code is None:
            return None
        try:
            return STATE_NAMES[CleaningState(code)]
        except ValueError:
            return None

    @property
    def is_cleaning(self) -> bool:
        return self.state_code in (
            CleaningState.PLAY,
            CleaningState.RESUMED,
            CleaningState.PLAY_SPECIAL,
            CleaningState.SUSPENDED,
        )

    @property
    def progress(self) -> int | None:
        """Cycle progress 0-100; None when no cycle is running (cloud sends 255)."""
        val = self.operation.get("progress")
        try:
            val = int(val)
        except (TypeError, ValueError):
            return None
        if val == PROGRESS_NONE or not 0 <= val <= 100:
            return None
        return val

    @property
    def connected(self) -> bool | None:
        val = self.raw.get("reportedStatus")
        return None if val is None else str(val).lower() == "connected"

    @property
    def washes_left(self) -> int | None:
        return self.raw.get("remainingSaniSolution")

    @property
    def sani_low(self) -> bool | None:
        left = self.washes_left
        return None if left is None else left <= LOW_WASHES_LEFT

    @property
    def last_clean(self) -> datetime | None:
        return parse_timestamp(self.raw.get("lastClean"))

    @property
    def active_errors(self) -> list[Any]:
        errs = self.raw.get("activeErrors")
        return errs if isinstance(errs, list) else ([errs] if errs else [])

    @property
    def main_error(self) -> Any:
        return self.raw.get("mainErrorType")

    # configuration ------------------------------------------------------------
    @property
    def mode(self) -> str | None:
        cfg = self._cfg
        if not cfg:
            return None
        if cfg.get("manual"):
            return MODE_MANUAL
        return MODE_TIME_ACTIVATION if cfg.get("mode") == 1 else MODE_CAT_ACTIVATION

    def config_for_mode(self, mode: str) -> dict[str, Any]:
        cfg = self.configuration
        if mode == MODE_MANUAL:
            cfg["manual"] = 1
        elif mode == MODE_TIME_ACTIVATION:
            cfg.update(manual=0, mode=1)
        else:
            cfg.update(manual=0, mode=0)
        return cfg

    def config_get(self, path: str) -> Any:
        """Dotted lookup into configuration, e.g. 'binaryElements.EXTRA_WASH'."""
        node: Any = self._cfg
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    def config_with(self, path: str, value: Any) -> dict[str, Any]:
        """Full configuration with one (dotted) key changed."""
        cfg = self.configuration
        node = cfg
        *parents, leaf = path.split(".")
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = value
        return cfg

    @property
    def schedule_utc(self) -> list[str]:
        sched = self._cfg.get("schedule")
        return list(sched) if isinstance(sched, list) else []
