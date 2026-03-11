"""Security helpers: password hashing + CSRF tokens.

No external dependencies (uses hashlib.pbkdf2_hmac).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PasswordHash:
    algo: str
    iterations: int
    salt_b64: str
    hash_b64: str

    def to_string(self) -> str:
        return f"{self.algo}${self.iterations}${self.salt_b64}${self.hash_b64}"

    @staticmethod
    def parse(s: str) -> "PasswordHash":
        parts = s.split("$")
        if len(parts) != 4:
            raise ValueError("Invalid password hash format")
        algo, iters_s, salt_b64, hash_b64 = parts
        return PasswordHash(algo=algo, iterations=int(iters_s), salt_b64=salt_b64, hash_b64=hash_b64)


def hash_password(password: str, *, iterations: int = 200_000, salt: bytes | None = None) -> PasswordHash:
    """Return a PBKDF2 hash record.

    algo format: pbkdf2_sha256$iters$salt_b64$hash_b64
    """
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    hash_b64 = base64.urlsafe_b64encode(dk).decode("ascii").rstrip("=")
    return PasswordHash(algo="pbkdf2_sha256", iterations=iterations, salt_b64=salt_b64, hash_b64=hash_b64)


def verify_password(password: str, ph_str: str) -> bool:
    try:
        ph = PasswordHash.parse(ph_str)
    except Exception:
        return False
    if ph.algo != "pbkdf2_sha256":
        return False

    # re-create hash
    salt = base64.urlsafe_b64decode(_pad_b64(ph.salt_b64))
    expected = base64.urlsafe_b64decode(_pad_b64(ph.hash_b64))
    got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ph.iterations)
    return hmac.compare_digest(got, expected)


def _pad_b64(s: str) -> str:
    # add '=' padding back
    return s + "=" * (-len(s) % 4)


def new_csrf_token() -> str:
    return base64.urlsafe_b64encode(os.urandom(24)).decode("ascii").rstrip("=")
