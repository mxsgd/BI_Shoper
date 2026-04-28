# Panel aktualizacji cen (CSV po kodach) - specyfikacja

## Cel

Zbudować panel w rozszerzeniu Shoper, który pozwala:
- masowo aktualizować ceny produktów na podstawie pliku CSV (mapowanie po kodzie produktu),
- śledzić postęp aktualizacji na żywo,
- przeglądać szczegółowe logi operacji,
- prezentować statystyki skuteczności (w tym procent sukcesu),
- pobrać logi w formacie CSV.

## Zakres funkcjonalny (MVP)

1. Upload pliku CSV.
2. Walidacja CSV (nagłówki, format danych, duplikaty kodów).
3. Start procesu aktualizacji cen.
4. Pasek postępu i statystyki w czasie rzeczywistym.
5. Widok logów (sukcesy/błędy/ostrzeżenia).
6. Eksport logów do CSV.

## Format pliku CSV

### Wymagane kolumny
- `code` - kod produktu / wariantu (klucz mapowania),
- `price` - nowa cena.

### Opcjonalne kolumny
- `currency` - waluta (np. `PLN`),
- `price_type` - typ ceny (np. detaliczna, promocyjna), jeśli API to rozróżnia,
- `comment` - notatka techniczna (zapisywana w logu, opcjonalnie).

### Zasady walidacji
- `code` nie może być pusty.
- `price` musi być liczbą dodatnią.
- Separatory dziesiętne: obsłużyć `.` i `,` (normalizacja do formatu API).
- Duplikaty `code`:
  - domyślnie błąd walidacji i blokada startu,
  - opcjonalnie tryb "ostatni wpis wygrywa".
- Limit rozmiaru pliku (np. 5-20 MB) i limit liczby wierszy (np. do 50k w MVP).

## Flow użytkownika

1. Użytkownik otwiera panel "Aktualizacja cen".
2. Wgrywa plik CSV.
3. System pokazuje podsumowanie walidacji:
   - liczba rekordów poprawnych,
   - liczba rekordów błędnych,
   - lista błędów z numerem wiersza.
4. Użytkownik uruchamia aktualizację.
5. W trakcie procesu widzi:
   - licznik przetworzonych rekordów,
   - procent postępu,
   - liczbę sukcesów / błędów / pominięć.
6. Po zakończeniu:
   - status końcowy,
   - statystyki procentowe,
   - przycisk "Pobierz log CSV".

## Proponowany UI panelu

## 1) Sekcja uploadu i walidacji
- Przycisk: `Wybierz plik CSV`.
- Informacja o wymaganym formacie.
- Tabela błędów walidacji:
  - `row_number`,
  - `code`,
  - `error_message`.

## 2) Sekcja postępu
- Pasek postępu `%`.
- Metryki:
  - `Total`,
  - `Processed`,
  - `Success`,
  - `Failed`,
  - `Skipped`.
- Wskaźnik "success rate":
  - `success_rate = success / processed * 100%` (zaokrąglenie do 1-2 miejsc).

## 3) Sekcja logów
- Filtry: `All`, `Success`, `Error`, `Warning`, `Skipped`.
- Wyszukiwarka po `code`.
- Paginated table / virtualized list dla dużej liczby logów.

## 4) Akcje końcowe
- `Pobierz log CSV`.
- `Pobierz raport podsumowania` (opcjonalnie JSON/CSV).
- `Uruchom ponownie dla błędów` (opcjonalnie w kolejnej iteracji).

## Model logu (pojedynczy wpis)

Każdy rekord aktualizacji powinien zapisać minimum:
- `timestamp`,
- `job_id`,
- `row_number`,
- `code`,
- `old_price`,
- `new_price`,
- `status` (`SUCCESS`, `ERROR`, `SKIPPED`, `WARNING`),
- `message`,
- `http_status` (jeśli dotyczy),
- `request_id` / `trace_id` (jeśli dostępne).

## Statusy i statystyki

### Definicje
- `Total` - liczba rekordów wejściowych po walidacji.
- `Processed` - rekordy, które zakończyły przetwarzanie statusem końcowym.
- `Success` - rekordy z poprawną aktualizacją ceny.
- `Failed` - rekordy zakończone błędem.
- `Skipped` - rekordy pominięte (np. brak produktu, ta sama cena, brak uprawnień).

### Kluczowe metryki
- `success_rate = Success / Processed * 100%`
- `failure_rate = Failed / Processed * 100%`
- `coverage_rate = Processed / Total * 100%`

W UI pokazuj metryki zarówno jako liczby bezwzględne, jak i procenty.

## API i backend - propozycja endpointów

1. `POST /price-update/jobs`
   - tworzy job aktualizacji na podstawie CSV,
   - zwraca `job_id`.

2. `GET /price-update/jobs/{job_id}`
   - status joba + statystyki + progress.

3. `GET /price-update/jobs/{job_id}/logs`
   - listowanie logów (filtrowanie, paginacja).

4. `GET /price-update/jobs/{job_id}/logs/export.csv`
   - pobranie logów jako CSV.

5. (Opcjonalnie) `POST /price-update/jobs/{job_id}/retry-failed`
   - ponowienie tylko nieudanych rekordów.

## Architektura wykonania

- Job asynchroniczny (kolejka / worker), aby UI nie czekało na cały proces.
- Przetwarzanie batchowe (np. 50-200 rekordów na batch).
- Ograniczenie równoległości zgodnie z limitami API Shopera.
- Retry z backoff dla błędów chwilowych (`429`, `5xx`, timeout).
- Idempotencja:
  - unikalny `job_id`,
  - ochrona przed podwójnym wykonaniem tego samego joba.

## Obsługa błędów

Kategoryzacja błędów:
- Błędy walidacji wejścia (przed startem joba).
- Błędy mapowania (`code` nie znaleziony).
- Błędy API (auth, brak modułu, limit, timeout).
- Błędy danych biznesowych (niedozwolona cena, waluta, typ ceny).

Każdy błąd musi mieć czytelny `message` do UI oraz szczegóły techniczne w logu.

## Bezpieczeństwo i uprawnienia

- Endpointy dostępne tylko dla uprawnionych użytkowników panelu.
- Maskowanie danych wrażliwych w logach.
- Audyt: kto uruchomił job, kiedy, z jakiego pliku.

## Wydajność i ograniczenia

- Stronicowanie logów od początku (nie ładować całego logu do UI na raz).
- Dla dużych plików użyć streamingu parsera CSV.
- Dodać limity:
  - max rozmiar pliku,
  - max liczba rekordów,
  - max czas wykonania joba.

## Kryteria akceptacji (MVP)

1. Użytkownik może wgrać poprawny CSV i uruchomić aktualizację po `code`.
2. Panel pokazuje postęp i procent sukcesu w czasie rzeczywistym.
3. Każdy rekord ma log z czytelnym statusem i komunikatem.
4. Po zakończeniu można pobrać logi jako plik CSV.
5. Proces poprawnie raportuje błędy i nie blokuje całego joba przez pojedynczy błąd rekordu.

## Przykład CSV wejściowego

```csv
code,price,currency
ABC-001,129.99,PLN
ABC-002,149.00,PLN
XYZ-101,89,PLN
```

## Przykład CSV logów do pobrania

```csv
timestamp,job_id,row_number,code,old_price,new_price,status,message,http_status
2026-04-27T12:10:01Z,job_123,2,ABC-001,119.99,129.99,SUCCESS,Price updated,200
2026-04-27T12:10:02Z,job_123,3,ABC-002,149.00,149.00,SKIPPED,Price unchanged,200
2026-04-27T12:10:03Z,job_123,4,XYZ-101,,89.00,ERROR,Product code not found,404
```

## Następne kroki (po MVP)

- Tryb "dry run" (symulacja bez zapisu).
- Harmonogram aktualizacji (joby cykliczne).
- Powiadomienia e-mail/Slack po zakończeniu.
- Porównanie "przed vs po" i raport różnic.
- Obsługa wielu cenników / kanałów sprzedaży.
