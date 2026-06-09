# TradingAgents Web UI

FastAPI backend + React (Vite) frontend.

## Quick start

### 1 — Backend
```bash
cd web
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

### 2 — Frontend
```bash
cd web/frontend
npm install
npm run dev
```

Open **http://localhost:5173** — the Vite dev server proxies `/api/*` to the FastAPI backend automatically.

## Production build
```bash
cd web/frontend && npm run build   # outputs to web/frontend/dist/
uvicorn api:app --port 8000        # FastAPI serves the built React app from /
```
