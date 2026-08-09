"""SSRF-safety tests for shop_url validation."""

import pytest

from app.services.security.shop_url import (
    ShopUrlValidationError,
    rest_api_base,
    validate_shop_url,
)


def test_accepts_valid_https_shop_url():
    assert validate_shop_url("https://myshop.shoparena.pl") == "https://myshop.shoparena.pl"


def test_accepts_custom_domain_and_strips_path():
    assert validate_shop_url("https://www.sklep-mkfoam.pl/some/path?x=1") == (
        "https://www.sklep-mkfoam.pl"
    )


def test_rest_api_base():
    assert rest_api_base("https://myshop.pl") == "https://myshop.pl/webapi/rest"


@pytest.mark.parametrize(
    "url",
    [
        "http://myshop.pl",              # http without dev flag
        "ftp://myshop.pl",               # wrong scheme
        "myshop.pl",                     # no scheme
        "https://user:pass@myshop.pl",   # userinfo
        "https://localhost",             # localhost
        "https://127.0.0.1",             # loopback IP
        "https://10.0.0.5",              # private IP
        "https://192.168.1.10",          # private IP
        "https://169.254.169.254",       # link-local / metadata IP
        "https://[::1]",                 # IPv6 loopback
        "https://8.8.8.8",               # public IP literal (domain required)
        "https://myshop.pl:8080",        # non-default port
        "https://internalhost",          # not fully qualified
        "",                              # empty
    ],
)
def test_rejects_dangerous_urls(url):
    with pytest.raises(ShopUrlValidationError):
        validate_shop_url(url)


def test_http_allowed_only_with_dev_flag():
    assert validate_shop_url("http://devshop.example.com", allow_insecure=True) == (
        "http://devshop.example.com"
    )
    with pytest.raises(ShopUrlValidationError):
        validate_shop_url("http://devshop.example.com", allow_insecure=False)


def test_invalid_port_value():
    with pytest.raises(ShopUrlValidationError):
        validate_shop_url("https://myshop.pl:99999")
