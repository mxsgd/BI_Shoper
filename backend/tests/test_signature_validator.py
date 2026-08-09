"""Tests of the Shoper HMAC-SHA512 signature validator."""

import hashlib
import hmac as hmac_mod
import time
from unittest import mock

import pytest

from app.services.security.shoper_signature import (
    InvalidSignatureError,
    MissingParameterError,
    MissingSignatureError,
    ShoperSignatureValidator,
    StaleTimestampError,
    canonical_string,
)
from tests.conftest import TEST_SECRET, sign_params

VALID_PARAMS = {
    "action": "install",
    "application_code": "abc",
    "shop": "shop-123",
    "shop_url": "https://myshop.example.com",
    "trial": "0",
}

# Static vector: canonical string fixed by hand, HMAC precomputed offline.
STATIC_CANONICAL = (
    "action=install&application_code=abc&shop=shop-123"
    "&shop_url=https://myshop.example.com&trial=0"
)
STATIC_EXPECTED_HASH = (
    "3c8f5b03591342db609afc138e3ba82fe428c2935c2ba0246cce397448994c7f"
    "85197bcf4b94777f93293edd74444068fe1924c2649b7339f11a19273cbe67d0"
)


@pytest.fixture
def validator():
    return ShoperSignatureValidator(TEST_SECRET)


def test_static_test_vector(validator):
    assert canonical_string(VALID_PARAMS) == STATIC_CANONICAL
    assert validator.compute(VALID_PARAMS) == STATIC_EXPECTED_HASH
    validator.verify({**VALID_PARAMS, "hash": STATIC_EXPECTED_HASH})


def test_valid_signature_passes(validator):
    validator.verify(sign_params(VALID_PARAMS))  # no exception


def test_parameter_order_does_not_matter(validator):
    signed = sign_params(VALID_PARAMS)
    reordered = dict(reversed(list(signed.items())))
    validator.verify(reordered)


def test_single_value_change_rejected(validator):
    signed = sign_params(VALID_PARAMS)
    signed["shop"] = "other-shop"
    with pytest.raises(InvalidSignatureError):
        validator.verify(signed)


def test_bogus_signature_rejected(validator):
    with pytest.raises(InvalidSignatureError):
        validator.verify({**VALID_PARAMS, "hash": "00" * 64})


def test_missing_hash_rejected(validator):
    with pytest.raises(MissingSignatureError):
        validator.verify(dict(VALID_PARAMS))


def test_empty_hash_rejected(validator):
    with pytest.raises(MissingSignatureError):
        validator.verify({**VALID_PARAMS, "hash": "  "})


def test_missing_shop_rejected(validator):
    params = {k: v for k, v in VALID_PARAMS.items() if k != "shop"}
    with pytest.raises(MissingParameterError):
        validator.verify(sign_params(params))


def test_polish_and_special_characters(validator):
    params = {"shop": "sklep-łódź", "name": "zażółć gęślą jaźń & spółka = 100%"}
    validator.verify(sign_params(params))


def test_empty_values_are_signed(validator):
    params = {"shop": "shop-1", "note": ""}
    signed = sign_params(params)
    validator.verify(signed, required=("shop",))
    # ...but tampering with the empty value breaks the signature
    signed["note"] = "x"
    with pytest.raises(InvalidSignatureError):
        validator.verify(signed)


def test_extra_signed_parameters_are_included(validator):
    params = {**VALID_PARAMS, "extra_field": "value42"}
    validator.verify(sign_params(params))
    # signature over params WITHOUT extra must not validate WITH it
    signed_without = sign_params(VALID_PARAMS)
    with pytest.raises(InvalidSignatureError):
        validator.verify({**signed_without, "extra_field": "value42"})


def test_timestamp_fresh_and_stale(validator):
    now = time.time()
    fresh = sign_params({"shop": "shop-1", "place": "panel", "timestamp": str(int(now))})
    validator.verify_with_timestamp(fresh, max_age_seconds=300, now=now)

    stale = sign_params(
        {"shop": "shop-1", "place": "panel", "timestamp": str(int(now - 3600))}
    )
    with pytest.raises(StaleTimestampError):
        validator.verify_with_timestamp(stale, max_age_seconds=300, now=now)


def test_timestamp_not_a_number(validator):
    signed = sign_params({"shop": "shop-1", "timestamp": "not-a-number"})
    with pytest.raises(StaleTimestampError):
        validator.verify_with_timestamp(signed, max_age_seconds=300)


def test_comparison_uses_compare_digest(validator):
    signed = sign_params(VALID_PARAMS)
    with mock.patch(
        "app.services.security.shoper_signature.hmac.compare_digest",
        wraps=hmac_mod.compare_digest,
    ) as spy:
        validator.verify(signed)
    assert spy.called


def test_empty_secret_rejected():
    with pytest.raises(ValueError):
        ShoperSignatureValidator("  ")


def test_repr_does_not_leak_secret(validator):
    assert TEST_SECRET not in repr(validator)
