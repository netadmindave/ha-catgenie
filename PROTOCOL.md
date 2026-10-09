# CatGenie protocol notes (app 1.8.250)

Source: `com.petnovations` 1.8.250 XAPK. The app is React Native with a Hermes v96 bytecode bundle, decompiled with hermes-dec. Everything below was read from that bundle. The signing code was also cross-checked against a literal JavaScript port running real crypto-js 4.2.0.

## Cloud REST

Base URL: `https://iot.petnovations.com`. `GET config/v1/url` → `{url, env}` can override it.
Request URL = `base + "/" + uri [+ "/" + additionalPath]`.

| Name in app | Method | URI | Body / params |
|---|---|---|---|
| generateLoginCode | POST | `ums/v1/users/generateLoginCode/v2` | `{str1: pE("+<cc><number>")}` |
| loginByPhoneNumber | POST | `ums/v1/users/loginByPhoneNumber/v2` | `{str1, code}` → user data incl. `refreshToken` |
| refreshToken | POST | `facade/v1/mobile-user/refreshToken/v2` | `{refreshToken}` → `{token, ...}` |
| getMyDevices | GET | `device/device/v2` | `?useFleetIndexAndGetRealConnectivity=true` → `{thingList:[...]}` (type 0 = CatGenie) |
| deviceOperation | POST | `device/management/{manufacturerId}/operation` | `{state}` 1 play, 2 pause, 3 resume, 4 abort, 129 special |
| deviceConfig | PUT | `device/management/{manufacturerId}/configuration` | full configuration object |
| getNotifications | GET | `notification/v1/push/user` | |
| getMyCats | GET | `device/pet/user` | |
| getPetStatistics | GET | `device/history/account/pet/statistics` | |
| getThing | GET | `device/v1/thing` | |
| firmware update | PUT | `device/update` | |

Auth: `Authorization: Bearer <token>`. A 401 with `code: TOKEN_NOT_VALID` (or `message: Unauthorized`) triggers a refresh and one retry.

### Device object (confirmed against a real unit, fw 100.4.14R)

- Top level: `manufacturerId` (used in command paths), `name` (may have trailing spaces), `fwVersion`, `hwRevision`, `reportedStatus` (`connected`), `macAddress`, `bleConnectionId`, `lastClean` (naive ISO, UTC), `remainingSaniSolution` (washes left; the app warns at ≤ 30), `activeErrors` [], `mainErrorType`, `serviceLevel`, `connectionMode` (`WIFI`).
- `operationStatus`: `{state, progress}`. `state` is 0 idle, 1 play, 2 paused, 3 resumed, 4 abort, 129 special. `progress` is 0–100, and **255 means no cycle**.
- `configuration`:
  - `mode` (0 cat activation, 1 time activation) and `manual` (0/1)
  - `schedule` (array of **UTC** `"HH:mm:ss"`, up to 8, at least 2 h apart)
  - `dndFrom`/`dndTo` (UTC `"HH:mm:ss"`, max 10 h)
  - `catDelay` (seconds, 300–1800)
  - `childLock` (0/1)
  - `autoLock` (seconds, 300-second steps, 0–1800)
  - `volumeLevel` (1–7)
  - `catSense`
  - `binaryElements` `{EXTRA_WASH, EXTRA_SHAKE}`, `extraDry`
  - `timezone`, `dstFrom`, `dstTo`
  - `activation`, `lng`, `heater`, `water`, `pumpPctT`

  Writes send the whole object back.

## Request signing (anti-tamper)

Header names are stored reversed in the app (`revStr`).

- `X-PM-EN-DEC` = base64(AES-256-CBC(key, IV = 16×0x00, PKCS7, `"<ts>-<rand7 with one 'Z' inserted>"`)). If `floor(ts/100)` is odd, add 100 to `ts`.
- AES key = `P-3Rp6d81Kw9a3Z-CyvWH0WXRieyITk6`, derived from `seasonsPrep()` for env prod.
- `X-PM-EN-VER` = `1.0.0`
- `X-Render-T` = `<resource uri>/<ts>`. Uses the resource URI, *without* the additional path.
- `Y-PM-SG-B` = hex HMAC-SHA256(hmacKey, bodyStr + X-Render-T). bodyStr is computed for POST/PUT/PATCH only.
- `Y-PM-SG-P` = hex HMAC-SHA256(hmacKey, paramsStr + X-Render-T).
- `bodyStr`/`paramsStr` = `getspclSt(obj)`: values concatenated in **descending** `localeCompare` key order, skipping null/undefined/`imageContent`, with JS string coercion, spaces removed, lower-cased.
- The signing secret arrives in the response header `x-access-control-allow-headers`. To recover it: `f3` (A→9, `e,`→r, `,`→2, `-`→F), then `r4` (` A`→dc, ` `→5, `en`→w, drop `[aogT]`), then `myName` (drop every 3rd char). It must come out 84 chars long, and the app stores it in the keychain.
- hmacKey = `"Yt" + secret[56:84] + "x3"` (prod).
- Before a secret is known, the Y-PM-SG-* headers are omitted, matching the app.
- `pE()` (login phone) uses the same AES scheme with `'X'` inserted and no timestamp parity rule.

## BLE (GATT) — reference only

The integration does not use BLE. The unit only advertises during Wi-Fi setup.

Service `BF268159-A5D4-44D2-9EF3-350FB9B3ECC0` ("Cpanel"):
- `18701116-E846-42AB-AFA3-FE106916EEF6` CGCommand: write, then notify or read the reply
- `5B96457D-D796-48FE-9A43-ED505590393A` CGInfo: notify/read

Outgoing frame: `[total] + per message [transport(0=CM), id, len, payload...]`, where total is the sum of message lengths.
Incoming frame: `[total, ?, id, len, payload..., id, len, payload...]`.

| id | message | payload |
|---|---|---|
| 1 | CLEANING_STATE | out `[state]`; in `[cleaningStatus, progress]` |
| 7 | WIFI_CREDS | ssid\0 password\0 |
| 11 | WIFI_STATUS | out `[cmd,0]` (0 off, 1 scan, 2 connect wifi, 4 connect cloud); in `[state, code]` |
| 17 | LED_STATE | `[value]` |
| 18 / 19 | WIFI_SCAN_COUNT / ENTRY | LE int16 / index, ssid[32], auth, channel, rssi-256 |
| 20 | KEY_HASH | `[flags(0x80 valid), hash...]` |
| 21 | KEY_URL | url\0 (cert package download URL) |
| 250 | GET_DATA_COMMAND | `[ids...]` to request values |

Wi-Fi status codes: 0 ok, 1 no config, 2 fail, 3 busy, 4 timeout, 5 join fail, 6 auth fail, 7 associate fail, 8/9/10 key download/install progress/done, 11 MQTT disabled.
