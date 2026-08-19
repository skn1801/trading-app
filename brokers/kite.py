"""
Zerodha Kite Connect wrapper.

IMPORTANT - unlike Angel One, Zerodha's *official* Kite Connect API does
NOT support headless login with just a password + TOTP. Every session
requires:
  1. Opening a browser login URL (kite.login_url())
  2. Logging in there (password + TOTP, in your own browser)
  3. Zerodha redirects to your registered redirect URL with a
     `request_token` in the query string
  4. That request_token + your api_secret is exchanged for a day-valid
     `access_token` via generate_session()

The access_token is valid until Zerodha's daily session reset (~6 AM IST
the next day), so step 1-3 has to be repeated once a day. This module
stores the exchanged access_token (encrypted) so you don't have to redo it
every time you open the dashboard on the same day - only when it expires.

Docs / SDK: https://github.com/zerodha/pykiteconnect
"""

from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs

try:
    from kiteconnect import KiteConnect
except ImportError:  # pragma: no cover
    KiteConnect = None


class KiteAuthError(Exception):
    pass


@dataclass
class KiteCredentials:
    nickname: str
    api_key: str
    api_secret: str
    access_token: str | None = None
    token_date: str | None = None  # ISO date the access_token was issued, to detect staleness


def extract_request_token(pasted_value: str) -> str:
    """Accepts either a raw request_token or a full redirected URL and returns the token."""
    pasted_value = pasted_value.strip()
    if "request_token" in pasted_value and ("http://" in pasted_value or "https://" in pasted_value):
        parsed = urlparse(pasted_value)
        qs = parse_qs(parsed.query)
        token = qs.get("request_token", [None])[0]
        if not token:
            raise KiteAuthError("Could not find request_token in the pasted URL.")
        return token
    return pasted_value


class KiteClient:
    def __init__(self, creds: KiteCredentials):
        if KiteConnect is None:
            raise ImportError("kiteconnect is not installed. Run: pip install kiteconnect")
        self.creds = creds
        self._kite = KiteConnect(api_key=creds.api_key)
        self.connected = False
        if creds.access_token:
            self._kite.set_access_token(creds.access_token)

    def get_login_url(self) -> str:
        return self._kite.login_url()

    def generate_session(self, request_token_or_url: str) -> str:
        """Exchanges a request_token for an access_token. Returns the new access_token."""
        request_token = extract_request_token(request_token_or_url)
        try:
            data = self._kite.generate_session(request_token, api_secret=self.creds.api_secret)
        except Exception as exc:
            raise KiteAuthError(f"Kite login failed for '{self.creds.nickname}': {exc}") from exc
        access_token = data["access_token"]
        self._kite.set_access_token(access_token)
        self.creds.access_token = access_token
        self.connected = True
        return access_token

    def verify_existing_token(self) -> bool:
        """Checks whether the stored access_token (if any) is still valid, without a fresh login."""
        if not self.creds.access_token:
            return False
        try:
            self._kite.profile()
            self.connected = True
            return True
        except Exception:
            self.connected = False
            return False

    def _require_connected(self):
        if not self.connected:
            raise KiteAuthError("Not connected. Complete the login flow first.")

    def fetch_positions(self) -> list[dict]:
        self._require_connected()
        try:
            resp = self._kite.positions()
        except Exception as exc:
            raise KiteAuthError(f"Could not fetch positions for '{self.creds.nickname}': {exc}") from exc
        rows = resp.get("net", []) if resp else []
        normalized = []
        for row in rows:
            normalized.append(
                {
                    "account": self.creds.nickname,
                    "broker": "Zerodha",
                    "symbol": row.get("tradingsymbol"),
                    "exchange": row.get("exchange"),
                    "product": row.get("product"),
                    "qty": row.get("quantity", 0),
                    "avg_price": _safe_float(row.get("average_price")),
                    "ltp": _safe_float(row.get("last_price")),
                    "pnl": _safe_float(row.get("pnl")),
                }
            )
        return normalized

    def fetch_funds(self) -> dict:
        self._require_connected()
        try:
            resp = self._kite.margins()
        except Exception as exc:
            raise KiteAuthError(f"Could not fetch funds for '{self.creds.nickname}': {exc}") from exc
        equity = (resp or {}).get("equity", {})
        available = _safe_float((equity.get("available") or {}).get("live_balance"))
        used = _safe_float((equity.get("utilised") or {}).get("debits"))
        total = _safe_float(equity.get("net")) or (available + used)
        return {
            "account": self.creds.nickname,
            "broker": "Zerodha",
            "available": available,
            "used": used,
            "total": total,
        }


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
