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
| `backend/alembic/versions/` | Migracje: jedyne źródło zmian schematu w bazie. `0001_baseline` = cały schemat sprzed Alembica. |
| `backend/app/migrations.py` | Alembic z kodu: `upgrade_to_head()` (seed demo, testy) i sprawdzenie wersji schematu przy starcie aplikacji. |
| `backend/scripts/adopt_legacy_db.py` | Jednorazowo: przejęcie bazy zbudowanej starym `create_all` (patrz sekcja 5). |
| `backend/scripts/create_database.py` | Tworzy bazę PostgreSQL (np. `bi_shoper`) jeśli nie istnieje. |
| `backend/scripts/view_database.py` | Podgląd tabel w bazie (lista tabel, kolumny, liczba wierszy). |
| `backend/scripts/seed_dim_date.py` | Wypełnia `dim_date` (wymiar czasu) w zadanym zakresie lat. |
| `backend/.env.example` | Wzór zmiennych (w tym `DATABASE_URL` jeśli nadpisujesz domyślny URL). |
| `docs/ShoperAPI-Reference.md` | Mapowanie API Shoper → tabele RAW (referencja przy ewentualnym ręcznym ETL). |

Schematem zarządza wyłącznie Alembic. Backend przy starcie **nie tworzy tabel**: sprawdza tylko, czy baza jest na najnowszej migracji, i odmawia startu, jeśli nie jest.

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

- **Utworzenie tabel / aktualizacja schematu** (w katalogu `backend`):  
  `python -m alembic upgrade head`  
  To samo polecenie przy każdym deployu, przed startem aplikacji. `dev.ps1` robi to automatycznie.

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

## 5. Migracje (Alembic)

**Zmiana schematu:**

1. Zmień model w `backend/app/models/`.
2. `python -m alembic revision --autogenerate -m "opis zmiany"` — wygeneruje plik w `alembic/versions/`.
3. **Przeczytaj wygenerowany plik.** Autogenerate nie wykrywa m.in. zmian klucza głównego ani zmian nazw kolumn (widzi je jako usunięcie + dodanie = utrata danych). Jeśli zmiana dotyczy istniejących danych, dopisz ich przeniesienie (przykład: `0002_store_scoped_core_keys.py`).
4. `python -m alembic upgrade head`, potem commit modelu razem z migracją.

**Kontrola:** `python -m alembic check` porównuje modele z bazą na najnowszej migracji. CI uruchamia to na pustej bazie przy każdym pushu, więc model zmieniony bez migracji nie przejdzie.

**Baza sprzed Alembica** (zbudowana starym `create_all`, np. lokalna `bi_shoper`): nie uruchamiaj na niej `upgrade head` od zera — tabele już istnieją. Zamiast tego jednorazowo:

```bash
python scripts/adopt_legacy_db.py            # podgląd zmian, nic nie zmienia
python scripts/adopt_legacy_db.py --apply
```

Skrypt w jednej transakcji oznacza bazę jako `0001_baseline`, uruchamia kolejne migracje i dopasowuje dryf (kolumny, których `create_all` nigdy nie dodał, pozostałe po usuniętych kolumnach, indeksy). Bazy demo i testowe nie potrzebują tego kroku: seed buduje je od zera migracjami.

---

## 6. Schemat (skrót)

- **RAW:** `raw_orders`, `raw_order_items`, `raw_products`, `raw_customers`, `raw_payments`, `raw_shipments`, `raw_categories`, `raw_discounts` — staging 1:1 z API.
- **CORE:** `fact_orders`, `fact_order_items`, `dim_customers`, `dim_products`, `dim_categories`, `dim_date` — star schema. Klucze to `(store_id, id z Shopera)`: każdy sklep numeruje zamówienia/produkty od 1, więc samo id nie jest unikalne między sklepami. `dim_date` jest wspólne.
- **Konfiguracja:** `stores` (multi-sklep).
- **Legacy:** `orders`, `order_items`, `products`, `customers`, `product_snapshots`, `traffic_stats` — do stopniowego wycofania po pełnym ETL.

Szczegóły pól i relacji: modele w `backend/app/models/`.

---

## 7. Granica z resztą projektu

- **Backend (FastAPI)** używa tej samej bazy i modeli, ale dodaje: sync, ETL, scheduler, REST API. To nie jest „tylko zarządzanie DB”.
- **Panel analityczny** (workspace `analytics-embed`) **nie** zarządza bazą — tylko wywołuje API backendu i wyświetla dane w iframe w panelu admin Shoper; konfiguracja URL API po stronie panelu.

Ten dokument dotyczy wyłącznie **zarządzania samą bazą danych** w projekcie BI Shoper.
