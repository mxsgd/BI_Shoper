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

### Frontend (TODO)

```bash
cd frontend
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
- [ ] Frontend scaffold
- [ ] Frontend strony
