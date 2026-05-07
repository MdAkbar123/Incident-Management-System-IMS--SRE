# Incident Management System (IMS) – SRE Edition

A high-throughput, highly resilient **Incident Management System (IMS)** engineered using modern **Site Reliability Engineering (SRE)** principles.

The platform is designed to ingest, debounce, correlate, and process operational alerts at scale while remaining stable during cascading infrastructure failures and traffic spikes.

---

# 🚀 Core Features

## High-Throughput Alert Ingestion
Handles bursts of **10,000+ signals per second** using asynchronous worker pools and bounded in-memory queues.

## Distributed Debouncing
Groups duplicate alerts arriving within a configurable time window into a single actionable incident using Redis atomic operations:

```redis
SET NX EX
```

## Cascading Failure Correlation
Automatically detects upstream dependency failures and visually correlates related incidents for faster Root Cause Analysis (RCA).

### Example
- Database outage → API failures → Service degradation

## Strict Incident State Machine
Prevents incidents from being closed until a detailed RCA is submitted, enforcing operational discipline and postmortem workflows.

## Hot-Path Dashboard Caching
Serves live incident dashboards directly from Redis sorted sets to reduce database load during outage storms and high refresh traffic.

## Cascading Failure Correlation 
Uses a system dependency graph to automatically detect and group downstream symptoms under their upstream root cause, instantly cutting through alert storms.

---

# 🏗️ System Architecture

![alt text](<architecture diag 1.png>)

<br>

![alt text](<architecture diag 2.png>)

---

# 🧰 Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python + FastAPI |
| Frontend | React + Vite |
| Concurrency | `asyncio` Task Groups & Worker Pools |
| Relational Database | MySQL |
| ORM & Migrations | SQLAlchemy + Alembic |
| Cache & Debouncer | Redis |
| Audit Log Storage | MongoDB |
| Time-Series Metrics | InfluxDB |
| Load Testing | `pytest` + `httpx.AsyncClient` |

---

# 🛡️ Engineering Highlight – Backpressure & Resilience

An Incident Management System is usually under maximum stress exactly when the infrastructure is failing.

To remain available during outage storms, this IMS implements a **Two-Tiered Backpressure & Load Shedding Strategy**.

---

## Tier 1 — Noisy Neighbor Protection (Rate Limiting)

Implemented using the `slowapi` middleware.

If a degraded microservice or misconfigured client enters a retry loop and floods the ingestion endpoint, requests are isolated by IP.

### Mechanism

The API responds with:

```http
HTTP 429 Too Many Requests
```

along with a `Retry-After` header.

### Benefit

Protects healthy traffic from being impacted by a single noisy client.

---

## Tier 2 — System Overload Protection (Load Shedding)

The ingestion API is optimized for speed and never blocks while waiting for database writes.

Incoming signals are pushed into an in-memory bounded queue:

```python
asyncio.Queue(maxsize=50000)
```

### Mechanism

If the queue reaches capacity, the API immediately rejects additional requests with:

```http
HTTP 503 Service Unavailable
```

### Benefit

Prevents:
- Out-Of-Memory (OOM) crashes
- Worker exhaustion
- Complete service collapse

This ensures the IMS remains alive long enough to process already accepted workloads.

---

# 🛠️ Setup Instructions (Docker Compose)

The easiest way to run the complete IMS stack locally is using Docker Compose.

---

## Prerequisites

Install the following:

- Docker
- Docker Compose
- Python 3.10+
- Node.js & npm

---

# 1️⃣ Clone the Repository

```bash
git clone https://github.com/MdAkbar123/Incident-Management-System-IMS--SRE.git

cd Incident-Management-System-IMS--SRE
```

---

# 2️⃣ Start Backend Infrastructure

```bash
docker-compose up -d
```

This starts:

| Service | Port |
|---|---|
| MySQL | `3306` |
| Redis | `6379` |
| MongoDB | `27017` |
| InfluxDB | `8086` |
| FastAPI API | `8000` |

---

# 3️⃣ Run Database Migrations

```bash
cd backend && alembic upgrade head
```

---

# 4️⃣ Start the Backend

```bash
uvicorn main:app --reload --port 8000
```
---

# 5️⃣ Start the Frontend

```bash
cd ../frontend

npm install

npm run dev
```

Frontend URL:

```txt
http://localhost:3000
```

---

# 6 Verify Health Status

```bash
curl http://localhost:8000/health
```

Expected:
- API health
- Database connectivity
- Redis status
- MongoDB status
- InfluxDB status

---

# 🧪 Simulation & Load Testing

The repository includes scripts for resilience validation and stress testing.

---

## Outage Simulation with correlation features.

Simulates cascading failures and validates debouncing/correlation logic.

```bash
python scripts/simulate_outage.py
```

---

## Aggressive Load Test

Stress-tests ingestion throughput with 10,000+ signals.

```bash
python scripts/load_test.py
```

---

# 📡 Core API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/ingest` | Ingest raw alert signals |
| `GET` | `/incidents` | List active incidents |
| `GET` | `/incidents/{id}` | Get incident details |
| `GET` | `/incidents/{id}/timeline` | View incident timeline |
| `PUT` | `/incidents/{id}/status` | Transition incident states |
| `POST` | `/incidents/{id}/rca` | Submit Root Cause Analysis |

---

# 📊 Project Screenshots

## Live Dashboard

![Live Dashboard](livepage.png)

---

## Closed Incident View

![Closed Incident](Closed%20incident-1.png)

---

## Incident Resolution Tracking

![Resolution Tracking](resolvemarked.png)

---

## RCA Submission Page

![RCA Page](Rcapage.png)

---

## Incident Reports

![Reports](report.png)

---

# 📘 API Documentation

Interactive OpenAPI documentation is available when the application is running:

```txt
http://localhost:8000/docs
```

---

# 🎯 Project Goals

This project demonstrates production-grade engineering patterns commonly used in large-scale distributed systems:

- Backpressure handling
- Distributed coordination
- Event debouncing
- Failure correlation
- Operational resilience
- Queue-based async processing
- Hot-path caching
- Incident lifecycle enforcement

---

# 📌 Future Improvements

Potential roadmap enhancements:

- Kubernetes deployment manifests
- Prometheus + Grafana observability stack
- Kafka-based event streaming
- WebSocket real-time dashboards
- Multi-region failover
- PagerDuty / Slack integrations
- ML-powered anomaly detection

---

# 📄 License

This project is intended for educational, architectural, and portfolio demonstration purposes.