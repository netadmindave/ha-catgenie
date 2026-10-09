"""Request signing for the Petnovations (CatGenie) cloud API.

Recovered from the CatGenie Android app (com.petnovations 1.8.250, Hermes
bundle). Every request carries:

  X-PM-EN-DEC   AES-256-CBC(zero IV) of "<ms timestamp>-<random>", base64
  X-PM-EN-VER   "1.0.0"
  X-Render-T    "<resource uri>/<ms timestamp>"
  Y-PM-SG-B     HMAC-SHA256(body string + X-Render-T)    (once a secret is known)
  Y-PM-SG-P     HMAC-SHA256(params string + X-Render-T)  (once a secret is known)

The HMAC secret is delivered by the server in the response header
``x-access-control-allow-headers`` and de-scrambled client side.

This module has no Home Assistant dependencies so it can be unit tested.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import secrets
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# --- AES key -----------------------------------------------------------------
# App: seasonsPrep() -> wearingOut(env) picks a 14 char seed, slices it and
# appends getMessage("vyC"). For production ("prod", or any env that is not
# dev/staging) the seed is "3Rp6d81Kwp9a3Z" with index 9.


def _derive_aes_key() -> bytes:
    seed, idx = "3Rp6d81Kwp9a3Z", 9  # idx is odd, so it is used as-is
    suffix = ("eiRXW0HW" + "vyC")[::-1] + "yITk6"  # getMessage("vyC")
    key = (
        seed[idx : idx + 1].upper() + "-" + seed[:idx] + seed[idx + 1 :] + "-" + suffix
    )
    return key.encode()


AES_KEY = _derive_aes_key()  # 32 bytes -> AES-256
assert len(AES_KEY) == 32

APP_SIGNING_VERSION = "1.0.0"  # revStr("0.0.1")
# getCatsAndCG(): "56-Yt-x3" for prod -> key = "Yt" + secret[56:84] + "x3"
_PROD_KEY_RECIPE = (56, "Yt", "x3")
SECRET_HEADER = "x-access-control-allow-headers"
SECRET_LENGTH = 84

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXTZabcdefghiklmnopqrstuvwxyz"


def _random_string(length: int = 7) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def _add_char_random(text: str, char: str) -> str:
    pos = secrets.randbelow(len(text)) if text else 0
    return text[:pos] + char.upper() + text[pos:]


def _aes_b64(plaintext: str) -> str:
    padder = padding.PKCS7(128).padder()
    data = padder.update(plaintext.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(AES_KEY), modes.CBC(b"\x00" * 16)).encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode()


def aes_decrypt_b64(ciphertext_b64: str) -> str:
    """Inverse of the app's AES helper (used by tests/diagnostics)."""
    dec = Cipher(algorithms.AES(AES_KEY), modes.CBC(b"\x00" * 16)).decryptor()
    raw = dec.update(base64.b64decode(ciphertext_b64)) + dec.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(raw) + unpadder.finalize()).decode()


def encrypt_timestamp(now_ms: int) -> str:
    """App tE(): value for the X-PM-EN-DEC header."""
    if math.floor(now_ms / 100) % 2 != 0:
        now_ms += 100
    return _aes_b64(f"{now_ms}-{_add_char_random(_random_string(7), 'z')}")


def encrypt_phone(phone_e164: str) -> str:
    """App pE(): the 'str1' field used by the SMS login endpoints."""
    return _aes_b64(f"{phone_e164}-{_add_char_random(_random_string(7), 'x')}")


# --- signature string ("getspclSt") -----------------------------------------


def _js_str(value: Any) -> str:
    """Approximate JavaScript String(value) coercion."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return str(int(value))
        return repr(value)
    if isinstance(value, (list, tuple)):
        return ",".join(_js_str(v) for v in value)
    if isinstance(value, dict):
        return "[object Object]"
    return str(value)


def _locale_key(key: str) -> tuple[str, str]:
    # Close enough to ICU localeCompare for ASCII identifiers:
    # case-insensitive primary order, lowercase before uppercase on ties.
    return (key.casefold(), key.swapcase())


def special_string(obj: dict[str, Any] | None) -> str:
    """App getspclSt(): values in descending key order, no spaces, lower case."""
    if not obj:
        return ""
    out = ""
    for key in sorted(obj, key=_locale_key, reverse=True):
        val = obj[key]
        if val is None or key == "imageContent":
            continue
        out += _js_str(val)
    return out.replace(" ", "").lower()


# --- signing secret -----------------------------------------------------------


def _f3(text: str) -> str:
    return text.replace("A", "9").replace("e,", "r").replace(",", "2").replace("-", "F")


def _r4(text: str) -> str:
    text = text.replace(" A", "dc").replace(" ", "5").replace("en", "w")
    return "".join(c for c in text if c not in "aogT")


def _my_name(text: str) -> str:
    return "".join(c for i, c in enumerate(text) if (i + 1) % 3 != 0)


def secret_from_header(header_value: str | None) -> str | None:
    """De-scramble the signing secret; returns None unless it is 84 chars."""
    if not header_value:
        return None
    secret = _my_name(_r4(_f3(header_value)))
    return secret if len(secret) == SECRET_LENGTH else None


def hmac_key(secret: str) -> str:
    start, prefix, suffix = _PROD_KEY_RECIPE
    return prefix + secret[start : start + 28] + suffix


def check_it(key: str, message: str) -> str:
    """App checkIt(): hex HMAC-SHA256."""
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


def build_headers(
    *,
    uri: str,
    method: str,
    data: dict[str, Any] | None,
    params: dict[str, Any] | None,
    secret: str | None,
    now_ms: int,
) -> dict[str, str]:
    """Return the app's anti-tamper headers for one request."""
    render_t = f"{uri}/{now_ms}"
    headers = {
        "X-PM-EN-DEC": encrypt_timestamp(now_ms),
        "X-PM-EN-VER": APP_SIGNING_VERSION,
        "X-Render-T": render_t,
    }
    if secret and len(secret) == SECRET_LENGTH:
        body = special_string(data) if method.upper() in ("POST", "PUT", "PATCH") else ""
        key = hmac_key(secret)
        headers["Y-PM-SG-B"] = check_it(key, body + render_t)
        headers["Y-PM-SG-P"] = check_it(key, special_string(params) + render_t)
    return headers
