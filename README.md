# BI Shoper

BI Shoper demonstrates an end-to-end e-commerce analytics workflow:

- API-based data ingestion from Shoper and GA4
- PostgreSQL RAW/CORE warehouse-style modeling
- FastAPI analytics backend exposing business metrics
- React + TypeScript embedded admin dashboard
- Operational tools for bulk price updates and sync monitoring
- Scheduled background jobs and token renewal logic

The project is designed to show practical BI, analytics engineering, backend integration, and e-commerce reporting skills in one vertical product

## Business Problem

Small and mid-sized Shoper stores often rely on fragmented reports from the store admin, GA4, spreadsheets, and manual exports. This makes it difficult to answer operational questions such as:

- Which products and categories drive revenue?
- Which customers are returning and which cohorts retain best?
- How do traffic sources translate into orders?
- Where does the cart or checkout funnel lose users?
- How can bulk price changes be validated before being applied?

BI Shoper centralizes these workflows into one analytics and operations panel.

## Data Model & Reliability

## Current Status

This is an actively developed portfolio/product prototype.

Implemented:

- Shoper API sync client with pagination, retry logic, and token renewal
- PostgreSQL RAW and CORE data layers
- FastAPI analytics backend
- React + TypeScript embedded analytics panel
- GA4 traffic ingestion
- Tracker/event pipeline groundwork
- APScheduler-based background jobs
- CSV bulk price update workflow with validation, progress tracking, logs, and exports

In progress:

- Partner API OAuth installation flow
- Alembic-based migration workflow
- Docker Compose local environment
- Demo dataset for portfolio review
- CI pipeline for backend and frontend checks
- Production deployment documentation
  
## Panel Preview

Embedded analytics panel for Shoper store admins — React dashboard inside the Shoper admin iframe:

| Dashboard | Orders |
| :---: | :---: |
| ![Dashboard — KPI overview and revenue trends](docs/DashboardScreen.png) | ![Orders — revenue, status and category breakdown](docs/ZamowieniaScreen.png) |

| Customers | Traffic |
| :---: | :---: |
| ![Customers — segments and top buyers](docs/KlienciScreen.png) | ![Traffic — GA4 funnel and sessions vs orders](docs/RuchScreen.png) |

| Trends | Price updates |
| :---: | :---: |
| ![Trends — seasonality and weekday patterns](docs/TrendyScreen.png) | ![Price updates — CSV bulk update with live progress](docs/AktualizacjaCenScreen.png) |

## What It Does

- Pulls commerce data from the Shoper REST API into a local PostgreSQL warehouse
- Stores source data in a RAW layer and transforms it into a CORE analytics model
- Exposes analytics endpoints for revenue, customers, cohorts, RFM, traffic, and cart funnel views
- Renders an embedded analytics dashboard for store admins using React + Recharts
- Syncs GA4 traffic data into dedicated raw tables
- Supports CSV-based bulk price updates with validation, progress tracking, and logs
- Runs scheduled background sync jobs with APScheduler

## Architecture

```mermaid
graph TD
    A[Shoper API] --> B[Sync Services]
    G[GA4 Data API] --> B
    T[Tracker Events] --> D[(PostgreSQL)]
    B --> D
    D --> E[Transform Layer]
    E --> D
    D --> F[FastAPI Analytics API]
    F --> H[React Admin Panel]
```

## Main Features

### Data ingestion
- Incremental sync for orders, products, customers, and reference data
- RAW staging tables for source-level traceability
- CORE/star-schema style tables for analytics queries

### Analytics API
- KPI overview
- Revenue trends
- Top products
- Customer analytics
- Cohorts and retention
- RFM segmentation
- Channel and traffic reporting
- Cart and funnel diagnostics

### Admin panel
- React + TypeScript + Vite frontend
- Embedded in Shoper admin as an iframe app
- Multiple analytics views such as dashboard, orders, customers, traffic, trends, retention, and cart
- Manual refresh/sync flow with persisted sync status after page reload

### Operations tooling
- APScheduler-based background jobs
- Automatic Shoper token renewal through `POST /auth` when WebAPI credentials are configured
- CSV price update workflow with validation, progress metrics, and exportable logs

## Tech Stack

- Backend: FastAPI, SQLAlchemy, APScheduler
- Database: PostgreSQL
- Frontend: React, TypeScript, Vite, Tailwind CSS, Recharts
- External data sources: Shoper REST API, Google Analytics 4, tracker events

## Repository Structure

```text
backend/            FastAPI app, sync services, analytics routes, DB models
analytics-embed/    React dashboard embedded in Shoper admin
tracker/            Tracker-related code and event pipeline work
docs/               Product notes, architecture docs, panel screenshots, and specs
PLAN.md             High-level architecture and data model notes
PRICE_UPDATE_PANEL_SPEC.md
```

## Local Development

### Requirements

- Python 3.12+
- PostgreSQL 15+
- Node.js 18+

### 1. Start the backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The backend health check is available at:

```text
http://localhost:8000/api/health
```

Swagger docs are available at:

```text
http://localhost:8000/docs
```

### 2. Start the frontend

```bash
cd analytics-embed
npm install
npm run dev
```

### 3. Convenience script

From the repo root, you can use:

```bash
.\dev.bat
```

This starts the backend in a separate PowerShell window and then runs the frontend.

## Environment Configuration

Create `backend/.env` and add the values you need. Minimal example:

```env
DATABASE_URL=postgresql+asyncpg://postgres:2402@localhost:5432/bi_shoper

GA4_PROPERTY_ID=
GA4_CREDENTIALS_PATH=

SHOPER_STORE_1_LOGIN=
SHOPER_STORE_1_PASSWORD=
```

Useful optional variables:

- `TRACKER_REMOTE_DATABASE_URL`
- `TRACKER_REMOTE_SSL_INSECURE`
- `SHOPER_DEFAULT_LOGIN`
- `SHOPER_DEFAULT_PASSWORD`

## Shoper Authentication Notes

The current Shoper integration does not yet use the full Partner API OAuth flow with refresh tokens.

Instead, the backend can automatically obtain a fresh access token from `POST /auth` when WebAPI credentials are available. Credentials can be provided:

- directly in store fields (`api_login`, `api_password`), or
- through environment variables such as `SHOPER_STORE_<id>_LOGIN` and `SHOPER_STORE_<id>_PASSWORD`

When the Shoper API returns `401 unauthorized_client`, the backend attempts to renew the token and persists the refreshed token metadata in the `stores` table.

## Current Status

Implemented:
- Shoper sync client with pagination and retry logic
- FastAPI analytics backend
- PostgreSQL RAW and CORE layers
- React analytics panel
- GA4 ingestion
- Scheduler-driven sync jobs
- Bulk price update panel and backend job processing

Still in progress:
- Full Partner API OAuth installation flow
- Formal migration workflow with Alembic
- Better deployment and production setup documentation

## Why This Project Is Interesting

This project sits at the intersection of:
- backend API design,
- ETL/data modeling,
- product analytics,
- ecommerce integrations,
- and admin dashboard UX.

It is a good example of building a vertical product end-to-end: from third-party API ingestion, through warehouse-style modeling, all the way to a user-facing analytics panel.

## Related Docs

- `PLAN.md`
- `docs/SHOPER_PANEL_APP.md`
- `docs/DB_MANAGEMENT.md`
- `PRICE_UPDATE_PANEL_SPEC.md`
- `docs/tracker-roadmap.md`

## License

This repository is proprietary and is released under an `All rights reserved` license.

See `LICENSE` for details.
