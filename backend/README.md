# Team Kiwi — Smart Lock Rental API (Phase 1)

Django + DRF skeleton prepared for **horizontal scaling on Render**: stateless web containers, Redis-backed Celery, MongoDB for domain data (wired in later phases), and health checks suitable for a load balancer.

## Layout

- `config/` — project settings (`local` vs `production`), URLs, WSGI/ASGI, Celery app
- `apps/` — bounded contexts (`core`, `bookings`, `locks`, `payments`, `webhooks`, `notifications`)
- `services/` — Seam, Square (`services/square_service.py`), Mongo helpers
- `docker-compose.yml` — local web + worker + beat + Redis + MongoDB

## Local development

From the repo root, go into **`backend`** once (there is only one `backend` folder—do not `cd backend` again if your prompt already shows `...\teamkiwibackend\backend>`).

```powershell
cd path\to\teamkiwibackend\backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

If **`.venv` already exists**, skip `python -m venv .venv` and only run `.\.venv\Scripts\pip install -r requirements.txt` (recreating the venv is usually unnecessary).

**Windows: `Permission denied` on `.venv\Scripts\python.exe`** when running `python -m venv .venv` almost always means something is **locking** that file (another terminal, Cursor/VS Code terminal using the venv, or **OneDrive** syncing the Desktop folder). Fix:

1. Close every terminal and IDE panel that might be running Python from this project; in Cursor, pick a different Python interpreter or reload the window.
2. Delete the old venv, then recreate:
   ```powershell
   cd C:\Users\micah\Desktop\teamkiwibackend\backend
   Remove-Item -Recurse -Force .venv
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   ```
3. If `Remove-Item` still fails, reboot once, or create the venv **outside** Desktop (avoids OneDrive locks), e.g.  
   `python -m venv $env:USERPROFILE\.venvs\teamkiwibackend`  
   `& "$env:USERPROFILE\.venvs\teamkiwibackend\Scripts\pip" install -r requirements.txt`  
   then from `backend`:  
   `& "$env:USERPROFILE\.venvs\teamkiwibackend\Scripts\python" manage.py runserver`  
   In Cursor: **Python: Select Interpreter** → choose that `python.exe`.

Put secrets in **either** `backend\.env` **or** the repo root `teamkiwibackend\.env` (both are loaded; `backend\.env` wins if a key exists in both). Example:

```powershell
copy .env.example .env
```

Run Django with the **venv interpreter** (avoids `No module named 'django'` if you forgot to activate):

```powershell
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py createsuperuser
.\.venv\Scripts\python manage.py runserver
.\.venv\Scripts\python manage.py seam_verify
.\.venv\Scripts\python manage.py mongo_verify
```

Optional: `.\.venv\Scripts\activate` then plain `python manage.py ...` works for the rest of that terminal session.

**Common mistakes (PowerShell)**

1. **`No module named 'django'`** — You ran plain `python manage.py ...` (system Python). Use the same interpreter that worked for Seam: **`.\.venv\Scripts\python manage.py mongo_verify`** (or activate the venv first).
2. **`The 'from' keyword is not supported`** — You pasted **Python** code into the PowerShell prompt. PowerShell is not Python. To try `get_mongo_client()` interactively, run:
   ```powershell
   .\.venv\Scripts\python manage.py shell
   ```
   Then at the `>>>` prompt:
   ```python
   from services.mongo_client import get_mongo_client
   client = get_mongo_client()
   client.admin.command("ping")
   ```

### MongoDB

There is **no Django “Mongo plugin”** in this project: the app uses **PyMongo**. `services/mongo_client.get_mongo_client()` matches Atlas’s recommended **`ServerApi('1')`** for `mongodb+srv://` URIs. Django’s own database stays on SQLite for built-ins (admin, sessions); **bookings and rental data** will live in Mongo when those features are added.

You can set either **`MONGO_URI`** or **split variables** (see `.env.example`): `DATABASEUSERNAME`, `DATABASEPASSWORD`, `MONGO_CLUSTER_HOST`, optional `MONGO_DB_NAME` / `MONGO_APP_NAME`. If the password contains **`&`** or other reserved characters, split variables avoid manual URL-encoding; a raw `MONGO_URI` must encode those characters yourself.

**Option A — MongoDB Atlas (recommended for real deploys, free tier)**

1. Create a free account: [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register).
2. Create a **project** → **Build a cluster** (e.g. free **M0**).
3. **Database Access**: add a database user (username + password). Save the password somewhere safe.
4. **Network Access**: **Add IP Address** → for quick local testing you can use `0.0.0.0/0` (allows the world; tighten later). For production, add Render’s outbound IPs or `0.0.0.0/0` only if you also use Atlas **strong auth** (user/password in URI).
5. **Database** → **Connect** → **Drivers** → copy the URI. It looks like  
   `mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?appName=Cluster0`
6. Edit the URI: set your password (if it contains `@ # :` etc., [URL-encode it](https://www.mongodb.com/docs/atlas/troubleshoot-connection/#special-characters-in-password)). Prefer a **database name** in the path before `?`, e.g.  
   `mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/kiwiDB?retryWrites=true&w=majority`  
   If Atlas only gives you `...mongodb.net/?appName=...` with **no** `/dbname/`, set **`MONGO_DB_NAME=kiwiDB`** in `.env` — the app uses that for collections.
7. Put that string in **`.env`** as `MONGO_URI=...` (same for Render env vars).

Test:

```powershell
.\.venv\Scripts\python manage.py mongo_verify
```

**Option B — Docker Compose (local only)**

With `docker compose up`, Mongo listens at hostname `mongo` on the compose network. Use:

`MONGO_URI=mongodb://mongo:27017/kiwiDB`

**Option C — MongoDB installed on your PC**

`MONGO_URI=mongodb://localhost:27017/kiwiDB`

**Django admin** (`/admin/`): there is **no** default login. After `createsuperuser`, open `http://127.0.0.1:8000/admin/` and sign in with that account. On Render, run `createsuperuser` via a one-off shell or release command against the same database your web service uses (SQLite on disk is ephemeral there—use a persistent DB later if you need admin in production).

Health:

- Liveness: `GET http://127.0.0.1:8000/api/health/`
- Readiness (DB + Redis + Mongo): `GET http://127.0.0.1:8000/api/health/ready/`

### Docker Compose

```bash
cd backend
copy .env.example .env
docker compose up --build
```

Celery:

- Worker: `celery -A config.celery worker -l info`
- Beat: `celery -A config.celery beat -l info`

Use the same `DJANGO_SETTINGS_MODULE` and env vars as the web process.

## Production / Render

1. **MongoDB**: Use [MongoDB Atlas](https://www.mongodb.com/atlas) (or another managed cluster). Set `MONGO_URI` on every service that talks to the database (web + workers in later phases).
2. **Redis**: Render Redis instance or external URL in `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`.
3. **Web service**: Docker image from `backend/Dockerfile`. Set:
   - `DJANGO_SETTINGS_MODULE=config.settings.production`
   - `DJANGO_SECRET_KEY` (long random string)
   - `ALLOWED_HOSTS` (comma-separated, include your `*.onrender.com` hostname)
   - `CORS_ALLOWED_ORIGINS` (comma-separated frontend origins)
4. **Background workers**: Duplicate the image with **different start commands**:
   - Worker: `celery -A config.celery worker -l info --concurrency=2` (raise concurrency or run multiple worker instances as load grows)
   - Beat: **exactly one** beat process cluster-wide (`celery -A config.celery beat -l info`)
5. **Scaling**: Add more web instances behind Render’s load balancer; avoid storing session state on disk; keep uploads off local filesystem if you add them later (use object storage).

A starter blueprint lives at repo root: `render.yaml`. Adjust service names, plans, and secret env vars (`MONGO_URI`, payment keys, etc.) in the Render dashboard after the first deploy.

## Environment variables

See `.env.example`. Production settings **require** `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, and `CORS_ALLOWED_ORIGINS`.

## MongoDB (`kiwiDB`)

| Collection | Purpose | Keys / notes |
|------------|---------|----------------|
| **`bookings`** | Square checkout + customer + structured `booking` (visit dates, guests, pricing). | **Unique** `reference_id` (UUID from frontend). Stores `square_payment_id`, `receipt_url`, `payment_status` after charge. |
| **`lock_access_codes`** | 6-digit PINs, Seam metadata, optional `booking_id` later. | **Unique** `code`. |

Relationships are **document-based**: link future flows with explicit IDs (e.g. store `reference_id` on a lock code when a booking is paid).

## Square checkout (React Web Payments SDK)

Set **`SQUARE_LOCATION_ID`** in `.env` (Square Dashboard → Locations). **`SQUARE_APPLICATION_ID`** defaults from **`REACT_APP_SQUARE_APPLICATION_ID`** or **`SQUARE_APPLICATION_ID`**.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/square/config` | Returns `{ "applicationId", "locationId" }` for the card form. **503** + `{ "error" }` if not configured. |
| POST | `/api/square/payments` | Body: `sourceId`, `amountCents`, `currency`, `referenceId` (UUID), optional `note`, `customerName`, `customerEmail`, `customerPhone`, `booking` (must include `totalCents` matching `amountCents`). |

**Success (200):** `{ "success", "paymentId", "status", "receiptUrl", "referenceId", "booking" }`. **Errors:** `{ "error": "..." }` with 400 / 502 as appropriate.

**CORS (local):** `config.settings.local` allows `http://localhost:3000` and Vite `5173` by default.

## Lock codes (MongoDB + Seam)

**Flow:** the API generates a **random 6-digit** code (`secrets`), saves it in MongoDB (`kiwiDB.lock_access_codes`), then—if the request includes a Seam **`device_id`** (in JSON or env **`DEVICE_ID`** as default)—calls Seam [`/access_codes/create`](https://docs.seam.co/latest/api/access_codes/create) to program that PIN on the lock for `starts_at` → `expires_at`. The JSON response includes **`seam_sync`**: `ok` | `failed` | `skipped` (skipped when `device_id` is omitted or you pre-filled `seam_access_code_id`).

**Why you might not see a collection in Atlas:** MongoDB creates a collection on the **first insert**. Until you successfully **POST** at least one lock code, `lock_access_codes` will not appear. Confirm you are browsing database **`kiwiDB`** (not `test` or `admin`).

### Test the backend (no frontend)

With `runserver` on port 8000, PowerShell:

```powershell
# Minimal: starts now, expires 24h later (uses DEVICE_ID from .env if set)
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/lock-codes/" -Method POST -ContentType "application/json" -Body '{}'

# Named lock, same default window
$body = '{"lock_name": "Test lock"}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/lock-codes/" -Method POST -ContentType "application/json" -Body $body

# Custom duration (hours) or absolute expires_at still supported
$body = '{"valid_for_hours": 48, "lock_name": "Weekend"}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/lock-codes/" -Method POST -ContentType "application/json" -Body $body
```

Then in Atlas → **Browse Collections** → `kiwiDB` → **`lock_access_codes`**, or:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/lock-codes/lookup/?code=123456"
```

(Replace `123456` with the `code` from the create response.)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/lock-codes/` | Create code (default **now → +24h** if you omit time fields; or `expires_at` / `valid_for_hours`; optional `device_id`, `lock_name`, …) |
| GET | `/api/lock-codes/<id>/` | Fetch by MongoDB `id` |
| GET | `/api/lock-codes/lookup/?code=123456` | Fetch by six-digit code |

`status` is `pending`, `active`, or `expired` (updated on read when past `expires_at`).

## Seam (smart lock API)

Seam does **not** use a separate username/password for server calls: you create a **workspace API key** in the [Seam dashboard](https://console.seam.co/) and set `SEAM_API_KEY` in `.env` (or Render). Endpoint catalog: [Seam API docs](https://docs.seam.co/latest/api/).

Verify connectivity after setting the key:

```bash
python manage.py seam_verify
```

From code, use `apps.locks.seam.get_seam_service()` which returns a `SeamService` backed by `services/seam_service.py`.

## Roadmap

Webhooks (Square/Seam), email receipts, and tighter booking ↔ lock linking can build on the `bookings` + `lock_access_codes` collections.
