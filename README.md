# Payroll & Attendance — Multi-tenant PWA

Mobile-first **Payroll, Attendance & Leave** platform with a Super Admin → Employer → Employee → Accountant/Cashier role tree, multi-tenant data isolation, geo-fenced attendance with on-device blink-liveness, 26-day Indian payroll with PDF salary slips, WhatsApp + Email notifications, and a Hindi/English UI.

| Layer | Tech |
|------|------|
| Frontend | React 19 · Tailwind · MapLibre GL · face-api.js · PWA |
| Backend | FastAPI · Motor (async MongoDB) · ReportLab · PyJWT · bcrypt |
| Notifications | Resend (email) · Twilio (WhatsApp) |
| Storage | MongoDB |

```
┌────────────────┐   /api/*   ┌──────────────┐
│  React PWA     ├───────────►│   FastAPI    │
│  (mobile-first)│            │   uvicorn    │
└───────┬────────┘            └──────┬───────┘
        │ static                      │ Motor
        ▼                              ▼
   nginx CDN                      MongoDB
```

---

## Quick start (local development)

```bash
# 1. Backend
cd backend
cp .env.example .env                 # set JWT_SECRET, ADMIN_PASSWORD, optional Resend/Twilio keys
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# 2. Frontend (in another terminal)
cd frontend
cp .env.example .env                 # point REACT_APP_BACKEND_URL at your backend
yarn install
yarn start                           # http://localhost:3000

# 3. Mongo
docker run -d -p 27017:27017 -v mongodata:/data/db --name mongo mongo:7
```

Default Super Admin (auto-seeded on first boot): **`admin@payroll.app` / `admin123`** — change `ADMIN_PASSWORD` in `.env` before first deploy.

---

## One-command deploy with Docker

```bash
git clone <your-repo-url> payroll && cd payroll

# Configure
cp backend/.env.example backend/.env
$EDITOR backend/.env                  # JWT_SECRET, ADMIN_PASSWORD, RESEND_API_KEY, TWILIO_*

# Build & run (Mongo + backend + nginx-served frontend)
docker compose up -d --build

# Logs
docker compose logs -f backend
```

Browse the app at <http://localhost:3000>; API at <http://localhost:8001/api/health>.

For production, run nginx/Caddy in front of the two services (TLS termination + path-based routing) — see [Production reverse-proxy](#production-reverse-proxy) below.

---

## Project layout

```
.
├── backend/
│   ├── app/
│   │   ├── config.py        # All env vars in one place
│   │   ├── db.py            # Motor client + index bootstrap
│   │   ├── deps.py          # FastAPI auth dependencies
│   │   ├── security.py      # bcrypt + JWT + captcha tokens
│   │   ├── utils.py         # gen_id, indian_fmt, haversine, …
│   │   ├── main.py          # create_app() — wires routers, lifespan, CORS
│   │   ├── routes/          # auth · admin · employees · attendance · leaves · payroll
│   │   ├── services/        # email · whatsapp · pdf · audit · seed
│   │   └── schemas/         # All Pydantic request/response models
│   ├── server.py            # 1-line shim: from app.main import app
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/           # Login · AdminApp · EmployerApp · EmployeeApp
│   │   ├── components/      # Shell, ui/Primitives, FaceLiveness, GeofenceMap
│   │   ├── contexts/        # AuthContext, I18nContext (en/hi)
│   │   ├── lib/             # api.js · useConfirm.jsx
│   │   ├── App.js · index.js
│   ├── public/              # manifest.json · service-worker.js · icons
│   ├── package.json
│   ├── Dockerfile
│   ├── nginx.conf
│   └── .env.example
└── docker-compose.yml
```

---

## Roles & permissions

| Role | Where | Can do |
|------|-------|--------|
| `super_admin` | Single platform user | Onboard employers, view audit log, toggle WhatsApp + backdate days |
| `employer` | One per tenant | Manage employees · approve leaves · approve & delete payroll · disburse · settings (geo-fence, leave types, working days) |
| `employee` | Per tenant | Mark attendance (today + 30-day backdate) · apply for leave · download own salary slips |
| `employee` + `accountant` | Elevated | Generate payroll · edit per-line deductions · submit for approval · view summary |
| `employee` + `principal` | Elevated | Approve / reject leaves on employer's behalf |
| `employee` + `cashier` | Elevated | Mark items as cash-disbursed |

Roles are additive — one user can be `accountant` + `cashier`.

---

## Feature flags (Super Admin → Platform)

| Flag | Default | Effect |
|------|---------|--------|
| `whatsapp_enabled` | `false` | Globally enables Twilio WhatsApp for leave-decision and salary-ready alerts |
| `max_backdate_days` | `30` | How far back employees can mark attendance |

---

## State machine — Payroll run

```
┌────────┐  submit   ┌──────────────────┐  approve ┌──────────┐  disburse all  ┌────────────┐
│ draft  ├──────────►│ pending_approval ├─────────►│ approved ├───────────────►│ disbursed  │
└───┬────┘ (accntnt) └────────┬─────────┘ (employer)└─────┬────┘ (cashier/emp) └─────┬──────┘
    │                          │ reject                  │ delete                   │ delete
    ▼                          ▼                          ▼                          ▼
 (regen)                    rejected                  (run gone — month unlocked)
```

Once `approved` or `disbursed`, that month is locked → employees can't edit attendance until employer **deletes** the run.

---

## Production reverse-proxy

`Caddyfile` example:

```caddy
your-domain.com {
  reverse_proxy /api/* localhost:8001
  reverse_proxy localhost:3000
}
```

Or with nginx:

```nginx
server {
  server_name your-domain.com;

  location /api/ {
    proxy_pass http://localhost:8001;
    proxy_set_header Host $host;
  }
  location / {
    proxy_pass http://localhost:3000;
  }
}
```

In the frontend `.env`, set `REACT_APP_BACKEND_URL=https://your-domain.com` so XHRs hit `/api/*` on the same origin.

---

## Free-tier deploy targets

| Layer | Easiest free option | Notes |
|-------|---------------------|-------|
| Backend | **Render** Web Service (free tier) · **Railway** · **Fly.io** | All read `Dockerfile`. Set env vars in dashboard. |
| Frontend | **Cloudflare Pages** (free) · **Vercel** · **Netlify** | Build cmd `yarn build`, output `build/`. Set `REACT_APP_BACKEND_URL` to your Render URL. |
| Mongo | **MongoDB Atlas** free 512 MB | Use the `mongodb+srv://` URL. Allow inbound IPs from Render. |
| Email | **Resend** 3 000/mo free | Verify your sender domain. |
| WhatsApp | **Twilio Sandbox** | Real numbers need template approval. |

---

## API surface

`GET  /api/health` · `GET /api/auth/captcha` · `POST /api/auth/login` · `GET /api/auth/me` · `POST /api/auth/logout`

Super-admin: `POST/GET/DELETE /api/admin/employers` · `GET /api/admin/audit` · `GET /api/admin/stats` · `GET/PUT /api/admin/platform-settings`

Tenant: `GET/PUT /api/tenant/settings` · `POST/GET/PUT/DELETE /api/employees` · `GET /api/employees/{id}`

Attendance: `POST /api/attendance/mark` · `POST /api/attendance/delete` · `GET /api/attendance/today` · `GET /api/attendance/history` · `GET /api/attendance/locked-months` · `GET /api/attendance/config`

Leave: `GET /api/leave/balances` · `POST /api/leave/apply` · `GET /api/leave/applications` · `POST /api/leave/applications/{id}/decision`

Payroll: `POST /api/payroll/generate` · `GET /api/payroll/runs` · `GET /api/payroll/runs/{id}` · `PUT /api/payroll/items/{id}/deductions` · `POST /api/payroll/runs/{id}/submit` · `POST /api/payroll/runs/{id}/approve` · `DELETE /api/payroll/runs/{id}` · `POST /api/payroll/items/{id}/disburse` · `GET /api/payroll/items/{id}/slip` · `GET /api/payroll/my` · `GET /api/payroll/runs/{id}/summary`

---

## Tests

```bash
cd backend
python -m pytest tests/backend_test.py -q
# 33 passed
```

---

## License

MIT — see `LICENSE`.
