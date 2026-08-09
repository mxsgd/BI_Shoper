import pytest
from cryptography.fernet import Fernet

from app.services.security.token_cipher import TokenCipher, TokenCipherError


def test_roundtrip():
    cipher = TokenCipher(Fernet.generate_key().decode())
    token = "very-secret-access-token"
    encrypted = cipher.encrypt(token)
    assert encrypted != token
    assert token not in encrypted
    assert cipher.decrypt(encrypted) == token


def test_missing_key_rejected():
    with pytest.raises(TokenCipherError):
        TokenCipher("")


def test_malformed_key_rejected():
    with pytest.raises(TokenCipherError):
        TokenCipher("not-a-fernet-key")


def test_wrong_key_cannot_decrypt():
    c1 = TokenCipher(Fernet.generate_key().decode())
    c2 = TokenCipher(Fernet.generate_key().decode())
    with pytest.raises(TokenCipherError):
        c2.decrypt(c1.encrypt("token"))


def test_repr_has_no_key_material():
    key = Fernet.generate_key().decode()
    cipher = TokenCipher(key)
    assert key not in repr(cipher)
