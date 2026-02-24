# Wishwave

Social wishlist web app with:
- owner accounts (email + password),
- OAuth login (Google),
- public share links without registration,
- gift reservation without duplicates,
- group funding for expensive gifts,
- realtime updates via WebSocket,
- URL auto-fill (title/image/price extraction).

## Stack

- Frontend: Next.js (App Router, TypeScript)
- Backend: FastAPI + SQLAlchemy (async)
- Database: PostgreSQL
- Infra: Docker Compose

## Product Decisions

- Owner privacy:
  - owner sees reservation/contribution counts only,
  - owner never sees participant identity in UI/API responses.
- Public access:
  - public wishlist link works for guests (no account required).
- Group funding:
  - enabled per item (`allow_group_funding`),
  - minimum contribution per item,
  - contribution cannot exceed remaining amount.
- Deleted item edge-case:
  - owner uses soft-delete (archive),
  - archived item remains visible in public list if any reservation or contribution already exists,
  - no new actions allowed on archived item.
- Incomplete funding:
  - item remains open until target reached or owner archives it manually.

## Local Run (Docker)

1. Copy env template:
```bash
cp .env.example .env
```

2. Start services:
```bash
docker compose up --build
```

3. Open:
- frontend: `http://localhost:3000`
- backend docs: `http://localhost:8000/docs`

## Local Run (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Run PostgreSQL locally and set:
- `DATABASE_URL=postgresql+asyncpg://wishlist:wishlist@localhost:5432/wishlist`

Example bootstrap (psql):
```sql
CREATE USER wishlist WITH PASSWORD 'wishlist';
CREATE DATABASE wishlist OWNER wishlist;
```

For Google OAuth set:
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/oauth/google/callback`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL` (default is `http://localhost:8000/api/v1`).

## Deploy Notes

Use two services + one Postgres database:
- backend service (FastAPI container),
- frontend service (Next.js container),
- managed PostgreSQL.

Required env vars:
- backend: `DATABASE_URL`, `JWT_SECRET`, `FRONTEND_URL`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`
- frontend build arg/env: `NEXT_PUBLIC_API_URL`

Realtime works out-of-the-box through backend WebSocket endpoint:
- `GET/WS /api/v1/public/ws/{share_slug}`
