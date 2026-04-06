# Zarządzanie bazą danych BI Shoper

Dokument wyodrębnia **wszystko, czego potrzeba do zarządzania samą bazą danych** (tworzenie, migracje, podgląd, seed) — bez logiki sync/ETL i API.

---

## 1. Zakres „zarządzanie bazą”

- **Tworzenie bazy** (np. `bi_shoper`) i tabel (schemat).
- **Podgląd** struktury i danych (skrypty, SQL).
- **Seed** danych referencyjnych (np. `dim_date`, opcjonalnie sklepy).
- **Konfiguracja** połączenia (URL, credentials).
- **Definicja schematu** (modele SQLAlchemy = źródło prawdy).

Nie wchodzi w to: sync z Shoper API, ETL RAW→CORE, scheduler, endpointy REST — to logika aplikacji.

---

## 2. Pliki i katalogi (w repozytorium)

| Ścieżka | Odpowiedzialność |
|---------|-------------------|
| `backend/app/config.py` | `database_url`, opcjonalnie `sync_database_url` (Alembic). Jedyna konfiguracja połączenia do DB. |
| `backend/app/database.py` | Silnik SQLAlchemy (async), sesja, `Base` dla modeli. |
| `backend/app/models/` | Definicja schematu: `store.py`, `raw/*.py`, `core/*.py`, oraz modele legacy (`order`, `product`, `customer`, `traffic`). |
| `backend/scripts/create_database.py` | Tworzy bazę PostgreSQL (np. `bi_shoper`) jeśli nie istnieje. |
| `backend/scripts/view_database.py` | Podgląd tabel w bazie (lista tabel, kolumny, liczba wierszy). |
| `backend/scripts/seed_dim_date.py` | Wypełnia `dim_date` (wymiar czasu) w zadanym zakresie lat. |
| `backend/.env.example` | Wzór zmiennych (w tym `DATABASE_URL` jeśli nadpisujesz domyślny URL). |
| `PLAN.md` | Opis architektury i schematu gwiazdy (RAW + CORE). |
| `docs/ShoperAPI-Reference.md` | Mapowanie API Shoper → tabele RAW (referencja przy ewentualnym ręcznym ETL). |

Baza jest tworzona przez backend przy starcie (`Base.metadata.create_all` w `main.py`), więc **uruchomienie aplikacji** też jest jednym ze sposobów „zarządzania” schematem (tworzenie tabel).

---

## 3. Zależności (Python)

Do uruchomienia skryptów DB (create, view, seed) potrzebne są:

- `sqlalchemy`
- `psycopg2-binary` (sync połączenie do PostgreSQL w skryptach)

Zainstalowane z `backend/requirements.txt`.

---

## 4. Typowe czynności

- **Utworzenie bazy** (np. pierwsza konfiguracja):  
  `python backend/scripts/create_database.py`  
  (parametry w skrypcie: host, port, user, password, nazwa bazy).

- **Utworzenie tabel** (schemat):  
  Uruchomienie backendu: `uvicorn app.main:app` (w katalogu `backend`) — przy starcie wywoływane jest `Base.metadata.create_all`.

- **Podgląd tabel:**  
  `python backend/scripts/view_database.py`  
  lub w pgAdmin/psql:  
  `SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;`

- **Wypełnienie `dim_date`:**  
  `python backend/scripts/seed_dim_date.py`  
  (zakres lat konfigurowalny w skrypcie).

- **Zmiana bazy (np. inna nazwa/port):**  
  Modyfikacja `database_url` w `backend/app/config.py` lub ustawienie zmiennej środowiskowej nadpisującej to ustawienie (zgodnie z `pydantic-settings`).

---

## 5. Schemat (skrót)

- **RAW:** `raw_orders`, `raw_order_items`, `raw_products`, `raw_customers`, `raw_payments`, `raw_shipments`, `raw_categories`, `raw_discounts` — staging 1:1 z API.
- **CORE:** `fact_orders`, `fact_order_items`, `dim_customers`, `dim_products`, `dim_categories`, `dim_date` — star schema.
- **Konfiguracja:** `stores` (multi-sklep).
- **Legacy:** `orders`, `order_items`, `products`, `customers`, `product_snapshots`, `traffic_stats` — do stopniowego wycofania po pełnym ETL.

Szczegóły pól i relacji: `PLAN.md`.

---

## 6. Granica z resztą projektu

- **Backend (FastAPI)** używa tej samej bazy i modeli, ale dodaje: sync, ETL, scheduler, REST API. To nie jest „tylko zarządzanie DB”.
- **Panel analityczny** (workspace `analytics-embed`) **nie** zarządza bazą — tylko wywołuje API backendu i wyświetla dane w iframe w panelu admin Shoper; konfiguracja URL API po stronie panelu.

Ten dokument dotyczy wyłącznie **zarządzania samą bazą danych** w projekcie BI Shoper.
