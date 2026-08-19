"""
Security helpers.

- The local app login password is hashed with bcrypt and never stored in
  plaintext, and never leaves the machine.
- Broker credentials (API keys, passwords, TOTP secrets, tokens) are
  encrypted with a Fernet key that is DERIVED from the app login password
  at login time using PBKDF2. The key itself is never written to disk -
  it only ever lives in memory (st.session_state) for the duration of the
  browser session. This means the encrypted broker credentials on disk
  are only ever readable by someone who knows your app login password.
"""

import base64
import json
import os

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PBKDF2_ITERATIONS = 390_000


def hash_password(password: str) -> str:
    """Hash a password for storage. Returns a utf-8 string safe for SQLite."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Corrupt/invalid hash
        return False


def generate_kdf_salt() -> str:
    """A random salt used to derive the encryption key. Safe to store alongside the user."""
    return base64.urlsafe_b64encode(os.urandom(16)).decode("utf-8")


def derive_encryption_key(password: str, kdf_salt_b64: str) -> bytes:
    """Derive a Fernet-compatible key from the login password + stored salt."""
    salt = base64.urlsafe_b64decode(kdf_salt_b64.encode("utf-8"))
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    key = kdf.derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(key)


def encrypt_dict(key: bytes, data: dict) -> str:
    """Encrypt a dict of broker credentials into an opaque token string."""
    f = Fernet(key)
    raw = json.dumps(data).encode("utf-8")
    return f.encrypt(raw).decode("utf-8")


def decrypt_dict(key: bytes, token: str) -> dict:
    """Decrypt a token back into a dict. Raises ValueError if the key is wrong."""
    f = Fernet(key)
    try:
        raw = f.decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError(
            "Could not decrypt stored credentials - wrong password or corrupted data."
        ) from exc
    return json.loads(raw.decode("utf-8"))
