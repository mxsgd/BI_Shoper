"""
Pobiera token z Shoper /auth:
  - SHOPER_MK_ACCESS_TOKEN w .env (bez pytania), albo
  - SHOPER_MK_LOGIN + SHOPER_MK_PASSWORD w .env, albo
  - interaktywnie: pyta o login i hasło, jeśli nie ma ich w .env.

Zapisuje ACCESS do docs/shops_config.py, aktualizuje stores.api_token w PostgreSQL,
robi test GET /products.

Uruchom z katalogu backend:
  python scripts/refresh_shoper_token.py
"""
import getpass
import os
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
_SHOPS_CONFIG = _REPO / "docs" / "shops_config.py"
os.chdir(_BACKEND)
sys.path.insert(0, str(_BACKEND))

try:
    from dotenv import load_dotenv

    load_dotenv(_BACKEND / ".env")
    load_dotenv(_BACKEND.parent / ".env")
except ImportError:
    print("pip install python-dotenv httpx sqlalchemy psycopg2-binary")
    sys.exit(1)

import httpx
from sqlalchemy import create_engine, text


def sync_db_url() -> str:
    from app.config import get_settings

    return get_settings().sync_db_url


def base_url() -> str:
    u = (os.environ.get("SHOPER_MK_API_URL") or os.environ.get("MKFOAM_API_URL") or "").strip().rstrip("/")
    return u or "https://www.sklep-mkfoam.pl/webapi/rest"


def obtain_token() -> str:
    existing = (os.environ.get("SHOPER_MK_ACCESS_TOKEN") or os.environ.get("MKFOAM_API_TOKEN") or "").strip()
    if existing:
        print("Używam SHOPER_MK_ACCESS_TOKEN / MKFOAM_API_TOKEN z .env (bez /auth).")
        return existing
    login = (os.environ.get("SHOPER_MK_LOGIN") or "").strip()
    password = (os.environ.get("SHOPER_MK_PASSWORD") or "").strip()
    if not login or not password:
        print("Brak SHOPER_MK_LOGIN / SHOPER_MK_PASSWORD w .env — podaj ręcznie (lub Ctrl+Z / Ctrl+D aby przerwać).")
        try:
            login = input("Login Shoper (konto z dostępem WebAPI): ").strip()
            password = getpass.getpass("Hasło: ").strip()
        except EOFError:
            print("\nBrak danych. Ustaw SHOPER_MK_LOGIN + SHOPER_MK_PASSWORD w backend/.env albo SHOPER_MK_ACCESS_TOKEN.")
            sys.exit(1)
    if not login or not password:
        print("Potrzebny login i hasło (albo SHOPER_MK_ACCESS_TOKEN w .env).")
        sys.exit(1)
    auth_url = f"{base_url()}/auth"
    with httpx.Client(timeout=25.0) as client:
        r = client.post(auth_url, auth=(login, password))
    if r.status_code != 200:
        print(f"Auth błąd {r.status_code}: {r.text[:400]}")
        sys.exit(1)
    token = r.json().get("access_token")
    if not token:
        print("Brak access_token:", r.json())
        sys.exit(1)
    print("Token pobrany z /auth OK.")
    return token


def write_access_to_shops_config(token: str) -> None:
    if not _SHOPS_CONFIG.is_file():
        print(f"Brak pliku: {_SHOPS_CONFIG}")
        sys.exit(1)
    text = _SHOPS_CONFIG.read_text(encoding="utf-8")
    safe = token.replace("\\", "\\\\").replace('"', '\\"')

    def _repl(m) -> str:
        return m.group(1) + safe + m.group(2)

    new_text, n = re.subn(
        r'("ACCESS"\s*:\s*")[^"]*(")',
        _repl,
        text,
        count=1,
    )
    if n != 1:
        print("Nie znaleziono pola ACCESS w docs/shops_config.py (oczekiwany wzorzec \"ACCESS\": \"...\").")
        sys.exit(1)
    _SHOPS_CONFIG.write_text(new_text, encoding="utf-8")
    print(f"Zapisano ACCESS w {_SHOPS_CONFIG}.")


def main():
    token = obtain_token()
    write_access_to_shops_config(token)

    store_id = int(os.environ.get("SHOPER_MK_STORE_ID", "1"))

    url = sync_db_url()
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE stores SET api_token = :t WHERE id = :id"),
            {"t": token, "id": store_id},
        )
    print(f"Zaktualizowano stores.api_token dla id={store_id}.")

    b = base_url()
    with httpx.Client(timeout=20.0) as client:
        test = client.get(
            f"{b}/products",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params={"limit": 1, "page": 1},
        )
    print(f"Test GET /products: HTTP {test.status_code}")
    if test.status_code != 200:
        print(test.text[:400])
        sys.exit(1)
    print("Pobieranie z API działa (przynajmniej pierwsza strona produktów).")


if __name__ == "__main__":
    main()
