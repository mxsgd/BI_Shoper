"""Encryption-at-rest for Shoper OAuth tokens.

Fernet (AES-128-CBC + HMAC-SHA256) keyed from an environment-provided key.
This is real authenticated encryption, not encoding: without the key the
ciphertext is useless.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class TokenCipherError(RuntimeError):
    """Raised when a token cannot be encrypted or decrypted."""


class TokenCipher:
    def __init__(self, key: str):
        key = (key or "").strip()
        if not key:
            raise TokenCipherError("Token cipher key is not configured.")
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            # Do not include the key material in the error message.
            raise TokenCipherError("Token cipher key is malformed (expected Fernet key).") from exc

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None:
            raise TokenCipherError("Cannot encrypt None.")
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt((ciphertext or "").encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise TokenCipherError("Stored token cannot be decrypted with the configured key.") from exc

    def __repr__(self) -> str:  # never leak key material
        return "<TokenCipher>"
