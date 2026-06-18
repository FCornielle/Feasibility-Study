# backend — API FastAPI

Encola estudios hacia el **worker persistente** de PowerFactory y sirve el modelo (subestaciones/mapa).
Backend y worker se comunican por una **cola en disco** (`JobStore`, `results/_jobs/`), sin infraestructura extra.

## Arranque (2 procesos)
```bash
# 1) Worker PF (Python 3.9, proceso persistente — UNA sola conexión al engine)
cd feasibility-study-app && python pf_worker/worker.py

# 2) API (otro terminal)
cd feasibility-study-app/backend
pip install -r requirements.txt
uvicorn app.main:app --reload      # http://localhost:8000/docs
```

## Endpoints
- `GET  /api/health` — vivo.
- `GET  /api/substations` — lista de subestaciones (nombre, kV, GPS) → `results/substations.json`.
- `GET  /api/grid` — GeoJSON de subestaciones + líneas → `results/grid_map.geojson`.
- `POST /api/runs` — encola un estudio. Body: `{substation, study?, pv_mw, bess_mw, bess_mwh, bess_mode}` → job `queued`.
- `GET  /api/runs` / `GET /api/runs/{id}` — estado/resultados.
- `WS   /api/ws/runs/{id}` — progreso en vivo hasta estado terminal (done/error).

## Flujo
`POST /runs` crea un job `queued` → el worker lo toma (`claim_next`), corre el estudio en PF reportando
progreso, y deja `done` con `result_file` (`results/<run_id>/<study>.json`) y `compliance`, o `error`.

## Tests (sin PowerFactory)
- `python backend/test_api.py` — API con TestClient (11/11).
- `python pf_worker/test_worker_loop.py` — bucle del worker con estudio simulado (9/9).
