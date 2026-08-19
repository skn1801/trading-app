"""
Angel One (SmartAPI) wrapper.

Angel One's official API supports fully headless login with
client_id + password/MPIN + a TOTP secret (the same secret you scan as a QR
code at https://smartapi.angelbroking.com/enable-totp), so this is fully
automated - no browser step needed, unlike Kite.

Docs / SDK: https://github.com/angel-one/smartapi-python
"""

from dataclasses import dataclass
import pyotp

try:
    from SmartApi import SmartConnect
except ImportError:  # pragma: no cover
    SmartConnect = None


class AngelOneAuthError(Exception):
    pass


@dataclass
class AngelOneCredentials:
    nickname: str
    api_key: str
    client_id: str
    password: str        # trading password / MPIN
    totp_secret: str      # the base32 secret behind the QR code


class AngelOneClient:
    """Thin wrapper around SmartConnect that normalizes outputs for the dashboard."""

    def __init__(self, creds: AngelOneCredentials):
        if SmartConnect is None:
            raise ImportError(
                "smartapi-python is not installed. Run: pip install smartapi-python"
            )
        self.creds = creds
        self._obj = None
        self.connected = False
        self.profile = None

    def connect(self):
        self._obj = SmartConnect(api_key=self.creds.api_key)
        try:
            totp_code = pyotp.TOTP(self.creds.totp_secret).now()
        except Exception as exc:
            raise AngelOneAuthError(f"Invalid TOTP secret for '{self.creds.nickname}': {exc}") from exc

        data = self._obj.generateSession(self.creds.client_id, self.creds.password, totp_code)
        if not data or not data.get("status"):
            message = (data or {}).get("message", "Unknown error")
            raise AngelOneAuthError(f"Angel One login failed for '{self.creds.nickname}': {message}")

        self.connected = True
        try:
            refresh_token = data["data"]["refreshToken"]
            self.profile = self._obj.getProfile(refresh_token)
        except Exception:
            self.profile = None
        return data

    def _require_connected(self):
        if not self.connected or self._obj is None:
            raise AngelOneAuthError("Not connected. Call connect() first.")

    def fetch_positions(self) -> list[dict]:
        """Returns a normalized list of position dicts."""
        self._require_connected()
        resp = self._obj.position()
        if not resp or not resp.get("status"):
            return []
        rows = resp.get("data") or []
        normalized = []
        for row in rows:
            try:
                qty = int(row.get("netqty", 0))
            except (TypeError, ValueError):
                qty = 0
            pnl = _safe_float(row.get("pnl") or row.get("m2mUnrealized") or row.get("unrealised") or 0)
            normalized.append(
                {
                    "account": self.creds.nickname,
                    "broker": "Angel One",
                    "symbol": row.get("tradingsymbol"),
                    "exchange": row.get("exchange"),
                    "product": row.get("producttype"),
                    "qty": qty,
                    "avg_price": _safe_float(row.get("avgnetprice")),
                    "ltp": _safe_float(row.get("ltp")),
                    "pnl": pnl,
                }
            )
        return normalized

    def fetch_funds(self) -> dict:
        """Returns normalized funds dict: available, used, total."""
        self._require_connected()
        resp = self._obj.rmsLimit()
        if not resp or not resp.get("status"):
            return {"account": self.creds.nickname, "broker": "Angel One", "available": 0.0, "used": 0.0, "total": 0.0}
        data = resp.get("data") or {}
        available = _safe_float(data.get("availablecash"))
        used = _safe_float(data.get("utiliseddebits"))
        total = _safe_float(data.get("net")) or (available + used)
        return {
            "account": self.creds.nickname,
            "broker": "Angel One",
            "available": available,
            "used": used,
            "total": total,
        }


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
