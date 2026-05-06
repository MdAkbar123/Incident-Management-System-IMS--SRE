# Incident Management System (IMS) — Phase 1

## Overview
Foundation & Infrastructure for the IMS backend.

## Quick Start

### 1. Start all four databases
```bash
docker-compose up -d
```

Wait ~30 seconds for all healthchecks to pass:
```bash
docker-compose ps   # all should show "healthy"
```

### 2. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 3. Run Alembic migrations
```bash
cd backend
alembic upgrade head
```

### 4. Start FastAPI
```bash
uvicorn main:app --reload --port 8000
```

### 5. Verify health
```bash
curl http://localhost:8000/health | python3 -m json.tool
```

Expected:
```json
{
    "status": "ok",
    "stores": {
        "mysql": true,
        "mongo": true,
        "redis": true,
        "influx": true
    }
}
```

## Architecture

- **MySQL**: Source of truth for Work Items and RCA records
- **MongoDB**: Raw signal audit log (high-volume data lake)
- **Redis**: Hot-path cache for real-time dashboard state
- **InfluxDB**: Time-series aggregations

## Database Schemas

### MySQL (SQL)
- `work_items`: Deduplicated incident records
- `rca`: Root cause analysis records

### MongoDB (NoSQL)
- `signals`: Raw error payloads (100s per Work Item possible)

## Files

```
.env                          # Environment variables
docker-compose.yml            # Four-container stack
backend/
  requirements.txt            # Python dependencies
  config.py                   # Settings from .env
  main.py                     # FastAPI app with lifespan
  models.py                   # SQLAlchemy models
  db/
    mysql.py, mongo.py, ...   # Connection managers
  routers/
    health.py                 # /health endpoint
  migrations/
    env.py                    # Alembic config
    versions/
      001_create...           # Initial schema
  alembic.ini                 # Alembic config file
```

## Next Steps (Phase 2)

- Signal ingestion API with debouncing logic
- Async queue processing
- Alert strategy pattern implementation
- Dashboard UI
