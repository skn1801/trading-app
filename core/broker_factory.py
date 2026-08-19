"""Builds live broker client objects from encrypted database rows."""

from core import security
from brokers.angel_one import AngelOneClient, AngelOneCredentials
from brokers.kite import KiteClient, KiteCredentials


def build_client(account_row: dict, enc_key: bytes):
    """account_row is a dict from database.get_broker_account / list_broker_accounts."""
    payload = security.decrypt_dict(enc_key, account_row["encrypted_payload"])
    broker = account_row["broker"]
    nickname = account_row["nickname"]

    if broker == "angel_one":
        creds = AngelOneCredentials(
            nickname=nickname,
            api_key=payload["api_key"],
            client_id=payload["client_id"],
            password=payload["password"],
            totp_secret=payload["totp_secret"],
        )
        return AngelOneClient(creds)

    if broker == "kite":
        creds = KiteCredentials(
            nickname=nickname,
            api_key=payload["api_key"],
            api_secret=payload["api_secret"],
            access_token=payload.get("access_token"),
            token_date=payload.get("token_date"),
        )
        return KiteClient(creds)

    raise ValueError(f"Unknown broker type: {broker}")


def payload_for_angel_one(api_key: str, client_id: str, password: str, totp_secret: str) -> dict:
    return {
        "api_key": api_key.strip(),
        "client_id": client_id.strip(),
        "password": password,
        "totp_secret": totp_secret.strip(),
    }


def payload_for_kite(api_key: str, api_secret: str, access_token: str = None, token_date: str = None) -> dict:
    return {
        "api_key": api_key.strip(),
        "api_secret": api_secret.strip(),
        "access_token": access_token,
        "token_date": token_date,
    }
