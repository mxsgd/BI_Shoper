# Shoper App Store — integracja Partner API (OAuth)

Dokument opisuje produkcyjną integrację BI Shoper z Shoper App Store:
instalację przez panel, autoryzację OAuth per sklep, iframe i migrację
z trybu legacy (login/hasło WebAPI).

---

## 1. Flow instalacji

Shoper **nie używa** browserowego flow `authorize → redirect_uri → callback`.
Zamiast tego wysyła podpisany **event lifecycle** (POST, form-encoded) na
skonfigurowany w Partner Portal endpoint aplikacji.

```
Merchant instaluje aplikację w App Store
   └─► Shoper: POST /api/shoper/app-store/event
       pola: action=install, application_code, application_version,
             auth_code (jednorazowy!), shop, shop_url, trial, hash
       └─► backend:
           1. weryfikuje HMAC-SHA512 (ShoperSignatureValidator)
           2. waliduje shop_url (HTTPS, bez userinfo/IP/localhost — anty-SSRF)
           3. tworzy/aktualizuje Store + ShoperAppInstallation (idempotentnie,
              unique na shoper_shop_id — reinstall nie tworzy duplikatu)
           4. wymienia auth_code:
              POST {shop_url}/webapi/rest/oauth/token
              Authorization: Basic base64(SHOPER_APP_ID:SHOPER_APP_SECRET)
              body: grant_type=authorization_code&code={auth_code}
           5. zapisuje access_token (90 dni) i refresh_token (180 dni)
              ZASZYFROWANE (Fernet, klucz SHOPER_TOKEN_CIPHER_KEY)
           6. oznacza sklep jako aktywny
```

`action=uninstall` → instalacja `uninstalled`, tokeny wyczyszczone,
`stores.is_active=False` (scheduler pomija sklep), dane analityczne RAW/CORE
zostają (soft delete). `action=upgrade` → aktualizacja `application_version`.

**Weryfikacja podpisu** (identyczna jak w `HashValidator` z
`dreamcommerce/appstore-sf-mvc-example@18c132d`):
parametry bez `hash` → sort alfabetyczny po kluczu → `key=value&key=value`
→ HMAC-SHA512 (hex) sekretem aplikacji → porównanie `hmac.compare_digest`.

Event lifecycle nie zawiera timestampa — ochrona przed replay opiera się na
idempotencji: `auth_code` jest jednorazowy, powtórka eventu z zużytym kodem
dla podłączonego sklepu zwraca 200 bez zmian, dla świeżej instalacji → 409.

## 2. Flow iframe

```
Panel Shoper ładuje iframe:
GET /api/shoper/app/entry?place=...&shop=...&timestamp=...&hash=...
   └─► backend:
       1. weryfikuje HMAC (te same reguły) + świeżość timestamp
          (okno SHOPER_IFRAME_MAX_AGE_SECONDS, domyślnie 300 s)
       2. mapuje shop → ShoperAppInstallation → lokalny Store
          (odinstalowany/nieaktywny sklep → 403)
       3. wystawia krótkotrwałą sesję aplikacji (HMAC-SHA256, TTL
          SHOPER_SESSION_TTL_SECONDS) w cookie:
          HttpOnly + Secure + SameSite=None (wymóg iframe)
       4. redirect 302 na SHOPER_PANEL_REDIRECT_URL
Frontend:
GET /api/shoper/app/session  →  { store_id, shop }
```

Frontend **nigdy nie otrzymuje tokenów Shoper API** — wszystkie requesty do
Shoper REST wykonuje backend. `store_id` pochodzi z podpisanej sesji, nie z
parametru przekazanego przez frontend (sklep nie może podszyć się pod inny).

## 3. Tokeny — wymiana i refresh

Serwis: `app/services/shoper_partner_auth.py` (`ShoperPartnerAuthService`).

* `exchange_auth_code()` — wymiana kodu instalacyjnego,
* `refresh_access_token()` — `grant_type=refresh_token`; refresh token jest
  **jednorazowy** — odpowiedź zawiera nową parę, stara jest nadpisywana
  atomowo (rotacja),
* `ensure_store_access_token()` — zwraca ważny token; odświeża gdy wejdzie
  w safety window (24 h przed wygaśnięciem). Równoczesne wywołania dla tego
  samego sklepu są serializowane per-store lockiem (asyncio.Lock) i po
  uzyskaniu locka warunek jest sprawdzany ponownie — do Shopera trafia
  jeden request,
* po `invalid_grant` / 400 / 401 instalacja przechodzi w `needs_reauth`
  (wymagany reinstall przez merchanta); błędy przejściowe (timeout, 429,
  5xx) mają ograniczone retry (maks. 2), błędy autoryzacyjne nie są
  ponawiane.

Dispatcher: `app/services/shoper_access.py::ensure_store_access_token` —
wybiera tryb per sklep:

| Tryb | Warunek |
|---|---|
| `partner_oauth` | aktywna instalacja App Store (zawsze ma pierwszeństwo) |
| `legacy_webapi` | brak instalacji **i** `SHOPER_ENABLE_LEGACY_WEBAPI=1` |
| `disconnected` | żadne z powyższych → kontrolowany błąd |

Sklep z instalacją App Store **nigdy** nie spada do legacy, nawet gdy ma
zapisane login/hasło.

## 4. Zmienne środowiskowe_safe_table_exists_sql

Patrz `backend/.env.example`. Wymagane przy `SHOPER_APPSTORE_ENABLED=1`
(walidowane przy starcie; komunikat błędu wymienia tylko NAZWY zmiennych):

| Zmienna | Opis |
|---|---|
| `SHOPER_APP_ID` | ID aplikacji z panelu developerskiego (OAuth client_id) |
| `SHOPER_APP_SECRET` | App Store secret — klucz HMAC + OAuth client_secret |
| `SHOPER_TOKEN_CIPHER_KEY` | klucz Fernet do szyfrowania tokenów w bazie |

Opcjonalne: `SHOPER_SESSION_SECRET`, `SHOPER_PANEL_REDIRECT_URL`,
`SHOPER_IFRAME_MAX_AGE_SECONDS`, `SHOPER_SESSION_TTL_SECONDS`,
`SHOPER_ALLOW_INSECURE_SHOP_URL` (tylko dev), `SHOPER_ENABLE_LEGACY_WEBAPI`.

Generowanie klucza szyfrującego:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 5. Konfiguracja w Shoper Partner Portal

1. Załóż konto partnera: https://partner.shoper.pl → utwórz aplikację.
2. Skonfiguruj:
   * **URL aplikacji (iframe/panel):** `https://twoja-domena.pl/api/shoper/app/entry`
   * **Webhook / event lifecycle URL:** `https://twoja-domena.pl/api/shoper/app-store/event`
   * **Callback URL:** nie występuje w tym flow (brak browserowego OAuth redirectu)
   * **Scopes:** odczyt zamówień, produktów, klientów; zapis produktów
     (aktualizacja cen, kody wariantów) — dobierz do funkcji panelu
3. Po utworzeniu aplikacji zapisz `app_id` i `app_secret` w zmiennych
   środowiskowych serwera (nigdy w repozytorium).
4. Produkcja wymaga HTTPS na obu URL-ach.

## 6. Devshop / rozwój lokalny

Wyłącznie jako środowisko developerskie wystaw lokalny backend przez tunel:

```bash
# Cloudflare Tunnel
cloudflared tunnel run --token <token>
# albo ngrok
ngrok http 8000
```

Adres tunelu wpisz w Partner Portal jako URL-e aplikacji testowej i ustaw
`SHOPER_ALLOW_INSECURE_SHOP_URL=1` tylko jeśli devshop nie ma HTTPS.

## 7. Testy

```bash
cd backend
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest tests -q
# z coverage nowego kodu autoryzacji:
.venv\Scripts\python.exe -m pytest tests -q --cov=app.services.security \
  --cov=app.services.shoper_partner_auth --cov=app.services.shoper_app_events \
  --cov=app.services.shoper_access --cov=app.routers.shoper_app
# migracje:
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic downgrade -1
.venv\Scripts\python.exe -m alembic upgrade head
```

Testy nie łączą się z prawdziwym Shoper API (respx/MockTransport) ani z
produkcyjną bazą (SQLite in-memory).

## 8. Ręczne QA w devshopie

1. Zainstaluj aplikację w devshopie → sprawdź w DB rekord
   `shoper_app_installations` (status `active`, tokeny zaszyfrowane —
   kolumny zaczynają się od `gAAAA`).
2. Otwórz panel w adminie Shopera → iframe ładuje frontend, cookie
   `bi_shoper_session` ustawione (HttpOnly/Secure/SameSite=None),
   `GET /api/shoper/app/session` zwraca `store_id`.
3. Uruchom sync (`quick`) → dane pobierają się bez loginu/hasła.
4. Zmień `token_expires_at` w DB na jutro → kolejny sync wykonuje refresh
   (w DB nowa para tokenów, `token_updated_at` zaktualizowany).
5. Odinstaluj aplikację → instalacja `uninstalled`, `stores.is_active=false`,
   scheduler pomija sklep, iframe zwraca 403.
6. Zainstaluj ponownie → ten sam rekord (bez duplikatu), status `active`.
7. Sprawdź logi — nie mogą zawierać tokenów, sekretów ani auth_code.

## 9. Rotacja sekretów

* **`SHOPER_APP_SECRET`** — rotacja w Partner Portal; zaktualizuj env i
  zrestartuj backend. Stare eventy podpisane starym sekretem przestaną
  przechodzić walidację (spodziewane).
* **`SHOPER_TOKEN_CIPHER_KEY`** — przed rotacją odszyfruj i ponownie
  zaszyfruj kolumny `*_encrypted` nowym kluczem (skrypt jednorazowy), albo
  wymuś `needs_reauth` i reinstalację sklepów. Bez tego stare tokeny będą
  nieodczytywalne (kontrolowany błąd `TokenCipherError`).
* **Legacy `api_login`/`api_password`** — po migracji sklepu na App Store
  usuń wartości z tabeli `stores` i zmiennych środowiskowych. Uwaga:
  historyczny `backend/.env` zawierał prawdziwe hasła — po wdrożeniu
  produkcyjnym zrotuj te hasła w Shoperze.

## 10. Migracja istniejących sklepów legacy

1. Zainstaluj aplikację App Store w sklepie merchanta.
2. Event `install` dopasuje się po `shop` (nowy rekord instalacji) — jeżeli
   sklep istniał już w `stores` z innym rekordem, dane analityczne można
   scalić przenosząc `store_id` (jednorazowa operacja SQL).
3. Zweryfikuj `auth_mode=partner_oauth` w `GET /api/stores/`.
4. Usuń `api_login`/`api_password` i wyłącz `SHOPER_ENABLE_LEGACY_WEBAPI`.

## 11. Wyłączenie legacy

Legacy (login/hasło → `POST /auth`) jest **domyślnie wyłączone**.
Aktywne tylko gdy `SHOPER_ENABLE_LEGACY_WEBAPI=1` i wyłącznie dla sklepów
bez instalacji App Store. Endpointy `POST /api/stores/` i
`PATCH /api/stores/{id}/auth` odrzucają zapisywanie loginu/hasła (HTTP 400),
gdy flaga jest wyłączona.
