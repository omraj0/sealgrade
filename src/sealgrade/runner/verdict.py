"""Verdict records and their signatures.

The controller computes the reward from validated, structured data and signs a record of what it
decided and from which inputs. The key lives in the controller process only; it is never placed in
any container. That makes a stored record tamper-evident: changing the reward, the artifact hash or
any other field invalidates the signature.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from collections.abc import Mapping
from typing import Any

KEY_ENV = "SEALGRADE_KEY"


def load_key() -> bytes:
    """The signing key: ``$SEALGRADE_KEY`` (hex) if set, otherwise a fresh per-process key."""
    configured = os.environ.get(KEY_ENV)
    if configured:
        try:
            key = bytes.fromhex(configured)
        except ValueError as exc:
            raise ValueError(f"{KEY_ENV} must be hexadecimal") from exc
        if len(key) < 16:
            raise ValueError(f"{KEY_ENV} must be at least 16 bytes")
        return key
    return secrets.token_bytes(32)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(record: Mapping[str, Any]) -> bytes:
    """A stable byte form of ``record`` (sorted keys, no whitespace, no NaN)."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sign(record: Mapping[str, Any], key: bytes) -> str:
    return hmac.new(key, canonical(record), hashlib.sha256).hexdigest()


def verify(record: Mapping[str, Any], signature: str, key: bytes) -> bool:
    return hmac.compare_digest(sign(record, key), signature)
