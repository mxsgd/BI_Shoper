# BI Shoper — Stan projektu

_Ostatnia aktualizacja: lipiec 2026_

---

## Co zostało zbudowane

### Panel analityczny (React + FastAPI)

| Zakładka | Status | Opis |
|---|---|---|
| **Dashboard** | ✅ gotowe | KPI (przychód, AOV, zamówienia, klienci), wykresy trendów, porównanie z poprzednim okresem, tryb focus-day |
| **Zamówienia** | ✅ gotowe | Revenue time-series, breakdown po statusach i kategoriach, top produkty |
| **Produkty** | ✅ gotowe | Top produkty po przychodzie/zamówieniach, filtry kategorii |
| **Klienci** | ✅ gotowe | Segmentacja RFM, top kupujący, nowi klienci miesięcznie, wskaźnik powrotów |
| **Trendy** | ✅ gotowe | Sezonowość dzienna/tygodniowa/miesięczna, heatmapa dni tygodnia |
| **Retencja** | ✅ gotowe | Cohort retention matrix (miesiące), wizualizacja tabel |
| **Ruch** | ✅ gotowe | GA4: sesje, konwersje, funnel, kanały; sesje vs zamówienia overlay |
| **Koszyk** | ✅ gotowe | Tracker-based funnel (add_to_cart → checkout → purchase), diagnostyka porzuceń |
| **Aktualizacja cen** | ✅ gotowe | CSV/XLSX/SQL bulk update z walidacją, progress live, logi, eksport CSV, **przycisk zatrzymania** |
| **Kody wariantów** | ✅ gotowe | Wykrywanie opcji Shoper, mapowanie suffixów, apply/dogeneruj, multi-product intersection |

---

### Backend (FastAPI + PostgreSQL)

**Routery:** `analytics`, `customers`, `dashboard`, `orders`, `products`, `stores`, `price_update`, `variant_codes`

**Warstwy danych:**
- **RAW** — surowe dane z Shoper API (tabele `raw_*`)
- **CORE** — gwiezdny schemat: `fact_orders`, `fact_order_items`, `dim_date`, `dim_product`, `dim_customer`, `dim_category`

**Serwisy:**
- `analytics_core/` — logika endpointów analitycznych podzielona na moduły (`overview`, `revenue`, `top_products`, `customers_analytics`, `trends`, `cohorts`, `rfm`, `common`)
- `price_update.py` — przetwarzanie jobów CSV (concurrent, z flagą cancel, logami, ETA)
- `price_update_persistence.py` — zapis jobów do DB po restarcie
- `shoper_client.py` — klient REST Shoper z rate-limitingiem, retry i auto-refresh tokenu
- `shoper_auth.py` — obsługa tokenu per sklep (`POST /auth`)
- `sync_service.py` — pełna i przyrostowa synchronizacja z Shoper API
- `transform_service.py` — transformacja RAW → CORE
- `ga4_client.py` — pobieranie danych GA4 do tabel RAW

**Scheduler:** APScheduler, dwa tryby synchroinzacji: `quick` (zamówienia + GA4 + transform) i `all` (pełna).

---

### Tracker (osobny serwis — `tracker/`)

Skrypt JS + microservice (Railway) zbierający eventy z frontend sklepu (page_view, add_to_cart, purchase, checkout steps). Dane trafiają do tabel trackera i są widoczne w zakładce Koszyk.

---

## Do zrobienia

### Priorytet wysoki

- [ ] **OAuth Partner API** — pełny flow instalacji aplikacji przez Shoper App Store (OAuth 2.0 z `client_id`/`client_secret`, callback `/auth/callback`, refresh_token). Aktualnie backend używa WebAPI login/password zamiast oficjalnego tokenu partnerskiego. Wymagane do opublikowania w App Store.
- [ ] **Rejestracja w Shoper Partner Portal** — założenie aplikacji partnerskiej, ustalenie `panel_url`, zakresy (`orders`, `products`, `analytics`), certyfikacja.
- [ ] **Alembic migracje** — formalny workflow migracji schematu DB. Aktualnie schemat tworzony skryptem `create_database.py`. Potrzebny `alembic init` + generowanie migracji przy każdej zmianie modeli.

### Priorytet średni

- [ ] **Deployment / produkcja** — dokumentacja i skrypty do wdrożenia na VPS/chmurę. Nginx reverse proxy, SSL, process manager (systemd/supervisor lub Docker Compose), zmienne środowiskowe.
- [ ] **Multi-tenant stores** — UI wyboru sklepu w panelu lub osobne instancje per klient. Aktualnie `store_id` jest hardcoded w zapytaniach.
- [ ] **Powiadomienia / alerty** — email lub webhook gdy job cenowy się posypie, albo sprzedaż spadnie poniżej progu.
- [ ] **Eksport danych** — CSV/XLSX z widoków analitycznych (zamówienia, klienci, top produkty).

### Tracker (z `tracker-roadmap.md`)

- [ ] **Stage 1 — `session_id`** (30-min inactivity timeout), rozszerzony `purchase` event (`order_id`, `value`, `currency`, `items[]`)
- [ ] **Stage 2 — stabilizacja eventów** — przejście z text-based heurystyk na `data-trk` atrybuty dla `add_to_cart`, `remove_from_cart`, `begin_checkout`
- [ ] **Stage 3 — intent events** — `view_item_list`, `select_item`, `search`, `filter`, `sort`; `checkout_error`, `payment_method`, `shipping_method`; analiza czasu między krokami checkout
- [ ] **Stage 4 — atrybucja** — pola UTM (`utm_source`, `utm_medium`, `utm_campaign`), `scroll_depth`, `time_on_page`

### Drobne usprawnienia

- [ ] Tabela `Traffic` — fallback gdy brak GA4 (np. wyświetl info zamiast błędu)
- [ ] Logi price update — opcja filtrowania po zakresie dat
- [ ] Kody wariantów — podgląd diff przed zastosowaniem (które kody zmienią się na co)
- [ ] Dodanie `comment` z pliku CSV do logu price update w UI
- [ ] Dashboard — możliwość pinowania ulubionego zakresu dat

---

## Struktura repozytorium

```
backend/                FastAPI app
  app/
    routers/            HTTP endpoints
    services/           logika biznesowa, klienci API
      analytics_core/   serwisy analityczne (overview, revenue, rfm, ...)
    models/             SQLAlchemy modele (raw/, core/, store, ...)
    scheduler/          APScheduler jobs
  scripts/              jednorazowe skrypty (seed, DQ checks, ...)

analytics-embed/        React dashboard (Vite + Tailwind + Recharts)
  src/
    pages/              Dashboard, Orders, Customers, ..., PriceUpdate, VariantCodes
    api.ts              klient HTTP do backendu
    App.tsx             routing + sidebar

tracker/                Tracker microservice (Railway)
  tracker.js            skrypt JS dla sklepu
  app/                  FastAPI event receiver

docs/                   dokumentacja, screenshoty, specs
```

---

## Shoper Auth — aktualny stan

Backend automatycznie odnawia token przez `POST /webapi/rest/auth` gdy API zwróci `401`. Dane logowania mogą być:
- w tabeli `stores` (`api_login`, `api_password`)
- w zmiennych środowiskowych: `SHOPER_STORE_<id>_LOGIN` / `SHOPER_STORE_<id>_PASSWORD`

**Docelowo** (App Store): token OAuth od Shoper Partner API, przechowywany per sklep z `refresh_token` i `expires_at`.
