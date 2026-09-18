"""Reference codes: the only link between a person and their report.

The code is shown once and never stored. We keep an HMAC with a server secret,
so a leaked table cannot be brute-forced back into codes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# Crockford base32: no I, L, O, U, so codes survive being read aloud or handwritten.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_LENGTH = 12  # 12 * 5 bits = 60 bits


def generate() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


def normalise(code: str) -> str:
    cleaned = code.upper().replace("-", "").replace(" ", "")
    return cleaned.replace("I", "1").replace("L", "1").replace("O", "0")


def is_wellformed(code: str) -> bool:
    cleaned = normalise(code)
    return len(cleaned) == _LENGTH and all(c in _ALPHABET for c in cleaned)


def digest(code: str, secret: str) -> str:
    return hmac.new(secret.encode(), normalise(code).encode(), hashlib.sha256).hexdigest()
