"""Async client for the Petnovations / CatGenie cloud API.

Endpoints, payloads and auth flow are taken from the official Android app
(com.petnovations 1.8.250). This module only depends on aiohttp so it can be
used and tested outside Home Assistant.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import aiohttp

from . import crypto
from .const import DEFAULT_BASE_URL, DEVICE_TYPE_GENIE

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=15)
USER_AGENT = "okhttp/4.12.0"

# (uri, method, requires auth)  -- names match the app's resource table
R_GET_BASE_URL = ("config/v1/url", "GET", False)
R_GENERATE_LOGIN_CODE = ("ums/v1/users/generateLoginCode/v2", "POST", False)
R_LOGIN_BY_PHONE = ("ums/v1/users/loginByPhoneNumber/v2", "POST", False)
R_REFRESH_TOKEN = ("mobile-user/refreshToken/v2", "POST", False)  # base + /facade/v1
R_GET_MY_DEVICES = ("device/device/v2", "GET", True)
R_DEVICE_OPERATION = ("device/management", "POST", True)
R_DEVICE_CONFIG = ("device/management", "PUT", True)
R_GET_NOTIFICATIONS = ("notification/v1/push/user", "GET", True)
R_GET_ACCOUNT = ("ums/v1/account/", "GET", True)
R_GET_MY_CATS = ("device/pet/user", "GET", True)


class CatGenieError(Exception):
    """Base error."""


class CatGenieAuthError(CatGenieError):
    """Authentication failed or the refresh token is no longer valid."""


class CatGenieApiError(CatGenieError):
    """The API returned an error."""

    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        self.body = body
        code = body.get("code") if isinstance(body, dict) else None
        msg = body.get("message") if isinstance(body, dict) else body
        super().__init__(f"HTTP {status}: {code or ''} {msg or ''}".strip())


def _find_key(obj: Any, *names: str) -> Any:
    """Depth-first search for the first matching key in nested JSON."""
    if isinstance(obj, dict):
        for name in names:
            if obj.get(name):
                return obj[name]
        for val in obj.values():
            found = _find_key(val, *names)
            if found:
                return found
    elif isinstance(obj, list):
        for val in obj:
            found = _find_key(val, *names)
            if found:
                return found
    return None


def _query_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class CatGenieClient:
    """Minimal re-implementation of the app's ApiService."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        refresh_token: str | None = None,
        signing_secret: str | None = None,
        base_url: str | None = None,
        on_credentials_changed: Callable[[], None] | None = None,
    ) -> None:
        self._session = session
        self.refresh_token = refresh_token
        self.signing_secret = signing_secret
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.access_token: str | None = None
        self._on_credentials_changed = on_credentials_changed
        self._refresh_lock = asyncio.Lock()

    # ------------------------------------------------------------------ core
    async def _raw_request(
        self,
        resource: tuple[str, str, bool],
        *,
        additional_path: str | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        base: str | None = None,
    ) -> tuple[int, Any]:
        uri, method, require_auth = resource
        path = uri if additional_path is None else f"{uri}/{additional_path}"
        url = f"{(base or self.base_url).rstrip('/')}/{path.lstrip('/')}"

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US",
            "User-Agent": USER_AGENT,
        }
        if require_auth:
            if not self.access_token:
                raise CatGenieAuthError("missing access token")
            headers["Authorization"] = f"Bearer {self.access_token}"
        headers.update(
            crypto.build_headers(
                uri=uri,
                method=method,
                data=data,
                params=params,
                secret=self.signing_secret,
                now_ms=int(time.time() * 1000),
            )
        )
        query = {k: _query_value(v) for k, v in (params or {}).items() if v is not None}

        _LOGGER.debug("%s %s params=%s data=%s", method, url, query, data)
        async with self._session.request(
            method,
            url,
            headers=headers,
            params=query or None,
            json=data if data is not None and method != "GET" else None,
            timeout=TIMEOUT,
        ) as resp:
            self._capture_secret(resp.headers.get(crypto.SECRET_HEADER))
            try:
                body: Any = await resp.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError):
                body = await resp.text()
            _LOGGER.debug("-> %s %s", resp.status, body)
            return resp.status, body

    def _capture_secret(self, header_value: str | None) -> None:
        secret = crypto.secret_from_header(header_value)
        if secret and secret != self.signing_secret:
            _LOGGER.debug("Received new request signing secret")
            self.signing_secret = secret
            self._notify()

    def _notify(self) -> None:
        if self._on_credentials_changed:
            self._on_credentials_changed()

    @staticmethod
    def _is_token_error(status: int, body: Any) -> bool:
        if status != 401:
            return False
        if not isinstance(body, dict):
            return True
        return body.get("code") == "TOKEN_NOT_VALID" or body.get("message") == "Unauthorized"

    async def request(
        self, resource: tuple[str, str, bool], **kwargs: Any
    ) -> Any:
        """Send a request, refreshing the access token once if needed."""
        if resource[2] and not self.access_token:
            await self.refresh_access_token()
        status, body = await self._raw_request(resource, **kwargs)
        if resource[2] and self._is_token_error(status, body):
            await self.refresh_access_token()
            status, body = await self._raw_request(resource, **kwargs)
        if status >= 400:
            if status in (401, 403):
                raise CatGenieAuthError(str(CatGenieApiError(status, body)))
            raise CatGenieApiError(status, body)
        return body

    # ------------------------------------------------------------------ auth
    async def discover_base_url(self) -> str:
        """GET config/v1/url -> {"url": ..., "env": ...}; falls back to default."""
        try:
            status, body = await self._raw_request(R_GET_BASE_URL, base=DEFAULT_BASE_URL)
            if status < 400 and isinstance(body, dict) and body.get("url"):
                self.base_url = str(body["url"]).rstrip("/")
                _LOGGER.debug("Base URL %s (env %s)", self.base_url, body.get("env"))
        except aiohttp.ClientError as err:
            _LOGGER.debug("Base URL discovery failed: %s", err)
        return self.base_url

    async def request_login_code(self, phone_e164: str) -> Any:
        """Ask the cloud to send an SMS login code."""
        return await self.request(
            R_GENERATE_LOGIN_CODE, data={"str1": crypto.encrypt_phone(phone_e164)}
        )

    async def login_with_code(self, phone_e164: str, code: str) -> dict[str, Any]:
        """Exchange the SMS code for a refresh token (and an access token)."""
        body = await self.request(
            R_LOGIN_BY_PHONE,
            data={"str1": crypto.encrypt_phone(phone_e164), "code": str(code).strip()},
        )
        refresh = _find_key(body, "refreshToken")
        if not refresh:
            raise CatGenieAuthError(f"login response had no refresh token: {body!r}")
        self.refresh_token = refresh
        access = _find_key(body, "token", "accessToken")
        if access and access != refresh:
            self.access_token = access
        self._notify()
        await self.refresh_access_token()
        return body if isinstance(body, dict) else {"data": body}

    async def refresh_access_token(self) -> None:
        if not self.refresh_token:
            raise CatGenieAuthError("no refresh token")
        async with self._refresh_lock:
            status, body = await self._raw_request(
                R_REFRESH_TOKEN,
                data={"refreshToken": self.refresh_token},
                base=f"{self.base_url}/facade/v1",
            )
            if status >= 400:
                raise CatGenieAuthError(f"token refresh failed: {status} {body!r}")
            token = _find_key(body, "token", "accessToken")
            if not token:
                raise CatGenieAuthError(f"refresh response had no token: {body!r}")
            self.access_token = token
            new_refresh = _find_key(body, "refreshToken")
            if new_refresh and new_refresh != self.refresh_token:
                self.refresh_token = new_refresh
                self._notify()

    # --------------------------------------------------------------- devices
    async def get_devices(self) -> list[dict[str, Any]]:
        body = await self.request(
            R_GET_MY_DEVICES, params={"useFleetIndexAndGetRealConnectivity": True}
        )
        things = body.get("thingList") if isinstance(body, dict) else None
        if things is None:
            things = _find_key(body, "thingList") or []
        return [
            t
            for t in things
            if isinstance(t, dict) and t.get("type", DEVICE_TYPE_GENIE) == DEVICE_TYPE_GENIE
        ]

    async def set_operation(self, manufacturer_id: str, state: int) -> Any:
        """POST device/management/{id}/operation {"state": n}."""
        return await self.request(
            R_DEVICE_OPERATION,
            additional_path=f"{quote(str(manufacturer_id), safe='')}/operation",
            data={"state": int(state)},
        )

    async def set_configuration(self, manufacturer_id: str, configuration: dict[str, Any]) -> Any:
        """PUT device/management/{id}/configuration <full configuration>."""
        return await self.request(
            R_DEVICE_CONFIG,
            additional_path=f"{manufacturer_id}/configuration",
            data=configuration,
        )

    async def get_notifications(self) -> Any:
        return await self.request(R_GET_NOTIFICATIONS)

    async def get_account(self) -> Any:
        return await self.request(R_GET_ACCOUNT)

    async def get_cats(self) -> Any:
        return await self.request(R_GET_MY_CATS)
