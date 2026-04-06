# Aplikacja w panelu administracyjnym Shopera

Aplikacja BI Shoper jest **aplikacją partnerską** osadzaną w panelu admin Shoper przez iframe (nie na stronie sklepu). Flow: OAuth 2.0, token per sklep, Shoper ładuje nasz URL w iframe.

---

## Jak działają aplikacje w panelu Shopera

- **Partner API** + **OAuth 2.0** + **iframe**.
- Aplikacja jest hostowana na naszym serwerze; Shoper wbudowuje ją do panelu przez iframe.
- **Rejestracja:** Shoper Partner Portal (partner.shoper.pl) → tworzysz aplikację → dostajesz `client_id`, `client_secret`.
- **Instalacja u klienta:** właściciel sklepu instaluje apkę → Shoper robi OAuth handshake i przekierowuje na nasz serwer.
- **Token:** nasz backend dostaje `access_token` dla konkretnego sklepu i zapisuje go w bazie (per sklep).
- **Panel:** Shoper ładuje nasz URL (z manifestu) w iframe wewnątrz panelu admina.

---

## Co musimy zbudować

### 1. Backend (nasz serwer)

| Element | Opis |
|--------|------|
| **OAuth callback** | Endpoint np. `/auth/callback` — odbiera kod/token od Shopera po instalacji lub odświeżeniu. |
| **Przechowywanie tokenów** | Tokeny per sklep w naszej bazie (np. rozszerzenie tabeli `stores`: `access_token`, `refresh_token`, `expires_at`). |
| **Shoper REST API** | Używamy tokenu danego sklepu do pobierania danych: zamówienia, produkty, kategorie, klienci. |
| **Zadania cykliczne** | Cron/scheduler (już mamy) — zbieranie danych do tabel RAW/CORE. |

### 2. Frontend (panel w iframe)

| Element | Opis |
|--------|------|
| **URL panelu** | Np. `https://twojaapka.pl/panel` — zdefiniowany w manifestie jako `panel_url`. |
| **Parametr sklepu** | Shoper może przekazać np. `?shop=nazwa-sklepu.pl` lub kontekst w iframe; frontend/backend identyfikuje sklep i dane. |
| **Treść** | Dashboard analityczny (wykresy sprzedaży, KPI, tabele) — React + Recharts, wywołania do naszego API. |

### 3. Manifest aplikacji (przy rejestracji w Partner Portal)

Przykład (struktura zależna od wymagań Shoper):

```json
{
  "panel_url": "https://twojaapka.pl/panel",
  "scopes": ["orders", "products", "analytics"]
}
```

`panel_url` — adres ładowany w iframe w panelu admina.

---

## Shoper REST API — dane do zbierania

- `/webapi/rest/orders` — zamówienia  
- `/webapi/rest/products` — produkty  
- `/webapi/rest/categories` — kategorie  
- `/webapi/rest/clients` — klienci (Users)

**Ruch na stronie (sesje, page views):** Shoper REST API tego bezpośrednio nie udostępnia. Można rozważyć własny skrypt trackingowy / webhook / GA4.

---

## Gdzie się zarejestrować i dokumentacja

- **Partner Portal:** https://partner.shoper.pl  
- **Dokumentacja API:** https://developers.shoper.pl  
- Konto partnera → utworzenie aplikacji → dostęp do testowego sklepu.

---

## Stack (zgodny z projektem)

| Warstwa | Technologia |
|---------|-------------|
| Backend/API | Python (FastAPI) — istniejący backend BI Shoper |
| Baza | PostgreSQL |
| Frontend panelu | React + Recharts (workspace `analytics-embed`) |
| Harmonogram | APScheduler (cron) — odpytuje Shoper API, zapis do RAW/CORE |
| Hosting | VPS / Azure / AWS |

---

## Różnica względem poprzedniego planu

- **Było:** osadzanie aplikacji na stronie sklepu (frontend dla klientów).  
- **Jest:** osadzanie **tylko w panelu administracyjnym** Shopera (iframe po OAuth); strona sklepu nie jest używana do embedu.

Niepotrzebne są elementy związane z osadzaniem na stronie sklepu (widget na front, snippet w sklepie itd.). Wystarczy `panel_url` i backend obsługujący OAuth + tokeny per sklep.
