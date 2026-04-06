# BI Shoper - Analiza biznesowa sklepow Shoper

Narzedzie do analizy biznesowej i ruchu na sklepach Shoper.

## Szybki start

### Wymagania
- Python 3.12+
- PostgreSQL 15+
- Node.js 18+ (frontend)

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Skopiuj .env.example -> .env i uzupelnij dane
copy .env.example .env

# Uruchom
uvicorn app.main:app --reload --port 8000
```

### Panel analityczny (iframe w panelu admin Shoper)

Panel jest w katalogu `analytics-embed/`; osadzamy go w panelu administracyjnym Shopera (OAuth + iframe), nie na stronie sklepu. Zob. `docs/SHOPER_PANEL_APP.md`.

```bash
cd analytics-embed
npm install
npm run dev
```

### API Docs
Po uruchomieniu backendu: http://localhost:8000/docs

## Status
- [x] Plan i architektura
- [x] Backend: config, database, modele
- [x] Backend: Shoper API client (z retry/pagination)
- [x] Backend: sync service
- [x] Backend: analytics service + API routes
- [x] Backend: scheduler
- [ ] Alembic migracje
- [ ] OAuth 2.0 / Partner API (panel w iframe)
- [x] Panel (analytics-embed): scaffold
- [ ] Panel: strony i wykresy
