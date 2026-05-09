# Payroll & Attendance PWA — PRD

## Original problem statement
> "read the pdf provided and ask for any changes in required in pdf. Use the fastest services but free tier. Use cloud flare pages, render etc if required. Let me know."

User shared a comprehensive **Payroll Build Guide v2** PDF: a multi-tenant payroll & attendance platform with super-admin / employer / employee / accountant / cashier roles, geo-fencing, facial verification, leave management, 26-day payroll, RazorpayX disbursement, salary slip PDFs, DPDP-compliance, etc.

## User choices (final)
- 100% mobile-first PWA
- React + FastAPI + MongoDB stack (Emergent default)
- Resend (email) — welcome email only
- Twilio WhatsApp (sandbox-ready, production-ready) — salary slip + leave decisions
- face-api.js liveness with blink challenge
- Hindi i18n (full app), with 🌐 toggle in header
- Visual math captcha on login
- 2-step confirmations on destructive / money flows
- Backdated attendance with employer-controlled day-window
- Full accountant workflow (deductions, submit-for-approval, summary view)
- Production refactor: modular `app/{config,db,routes,services,schemas}` backend + Docker

## Architecture
- **Backend** `/app/backend/` — FastAPI + Motor (async Mongo). Refactored into:
  - `app/config.py` — single env reader
  - `app/db.py` — Mongo client + `ensure_indexes()`
  - `app/security.py` — bcrypt + JWT + captcha tokens
  - `app/utils.py` — gen_id, indian_fmt, haversine, timezones
  - `app/deps.py` — auth dependencies
  - `app/services/` — `email`, `whatsapp`, `pdf`, `audit`, `seed`
  - `app/routes/` — `auth`, `admin`, `employees`, `attendance`, `leaves`, `payroll`
  - `app/main.py` — `create_app()` factory; lifespan seeds super admin + platform settings
  - `server.py` — 1-line shim that re-exports `app.main:app` for backward compat
- **Frontend** `/app/frontend/` — React 19 + Tailwind, mobile-first PWA
  - `contexts/AuthContext.js` — captcha-aware login, persists user
  - `contexts/I18nContext.jsx` — en/hi dictionaries + toggle
  - `lib/useConfirm.jsx` — promise-based 2-step confirmation hook (simple / type-to-confirm / re-enter password)
  - `pages/` — Login (captcha + lang toggle), AdminApp (Overview · Employers · Platform · Audit), EmployerApp (Overview · Employees · Leaves · Payroll · Settings), EmployeeApp (Home · History · Leaves · Salary)
  - `components/FaceLiveness.jsx`, `components/GeofenceMap.jsx` (MapLibre), `components/Shell.jsx`

## Deployment artifacts
- `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`
- `docker-compose.yml` — Mongo + backend + frontend with one command
- `backend/.env.example`, `frontend/.env.example`
- `README.md`, `DEPLOYMENT.md` — full guide for VPS / Render+CF Pages / k8s

## User personas
- **Super Admin** — operator. Onboards employers, sees platform stats, audit log, controls global feature flags (WhatsApp, max_backdate_days).
- **Employer** — workspace admin. Manages employees, attendance config, leave types, geo-fence. Approves leaves & payroll. Can delete approved payroll to unlock the month.
- **Accountant** (elevated employee) — generates payroll, edits per-line deductions, submits for approval, views summary.
- **Cashier** (elevated employee) — marks items as cash-disbursed.
- **Principal** (elevated employee) — can approve/reject leaves on behalf of employer.
- **Employee** — marks attendance (today + 30-day backdate, blink-liveness + GPS), applies leave, downloads own salary slips.

## Implemented (May 9, 2026 — v3 / DPDP + offline + cron)
**v3 additions**
- **Offline attendance queue** — IndexedDB store (`payroll-offline.attendance-queue`); when network call fails, mark is enqueued; auto-drains on `online` event + every 5 s; UI shows offline / "queued — syncing" banner.
- **DPDP consent screens** — `ConsentGate` blocks first login until employee accepts/declines 4 consent keys (`data_processing` mandatory · `face_capture` · `geo_location` · `whatsapp_email`). Privacy tab in employee app for live withdrawal, JSON data export, 30-day account erasure request + cancel. Backend enforces consent on `/api/attendance/mark` (face_capture + geo_location).
- **Privacy notice template** at `/app/PRIVACY_POLICY.md` — fill `{{COMPANY_LEGAL_NAME}}` etc. before going live.
- **Scheduled jobs (APScheduler, IST)** — 1st of every month at 02:00: auto-draft payroll for the previous month for every active tenant; daily at 03:00: process erasure requests past their 30-day notice window.
- **Backend route** `/api/me/privacy` (GET/PUT consents), `/api/me/data-export`, `/api/me/erasure-request` (POST/DELETE).
**Backend (33/33 tests pass)**
- Modular structure (no Emergent dependencies; works on any VPS / Render / Fly / k8s)
- Captcha-protected login + bcrypt + JWT
- Multi-tenant scoping (super admin sees all)
- Full payroll state machine: `draft → pending_approval → approved → disbursed`; `→ rejected`; `→ deleted` to unlock the month
- Per-line deduction editing (accountant only, only in draft)
- Backdated attendance with `max_backdate_days` flag, payroll-month lockout, `?overwrite=true` if month not finalized
- Leave decision endpoint with `decided_at_local` payload (local-tz timestamp from client)
- Cross-tenant isolation verified
- Audit log on every write
- **Email (Resend)**: only welcome email remains
- **WhatsApp (Twilio)**: leave-decision + salary-ready, gated by global `whatsapp_enabled` flag (Super Admin → Platform)

**Frontend**
- Login with **server-issued visual math captcha** + **🌐 EN/हिं toggle**
- Mobile fonts bumped (16px → 17px) + tap-targets (44px → 48px)
- **Hindi i18n** across login + nav + key pages (rest can be added incrementally)
- **2-step confirms**: type-name (delete employer/employee), type-month (delete payroll), re-enter-password (approve/reject payroll)
- **Backdated attendance UI** — date picker capped to `[today − maxBack, today]`, "Replace existing" toggle
- **Accountant Summary** screen — list & cards toggle, name + net salary view per employee
- **Super Admin → Platform Settings** page (WhatsApp toggle, max_backdate_days)
- Save Changes button on Leave Types editor — **bug fixed** (Button now defaults to `type="button"` instead of HTML `submit`)
- Local-timezone timestamps rendered via `Intl.DateTimeFormat`

## Mocked / Deferred
- **MOCKED**: Online payouts (RazorpayX) — returns `MOCK-XXXXXXXX` txn id
- **Deferred**: Voice verification (TFLite), offline attendance queue sync, raw-image facial verification for compliance, DPDP consent screens, bulk CSV employee import

## Backlog
- P1: RazorpayX Payouts (needs `RAZORPAYX_KEY_ID` + `RAZORPAYX_KEY_SECRET`)
- P1: Twilio production WhatsApp templates (currently sandbox-ready)
- P1: Hindi rendering across deeper screens (Employee history, Payroll table)
- P2: Bulk CSV employee import
- P2: Offline attendance queue (IndexedDB) + service-worker background sync
- P2: DPDP consent screens & data-export/erasure
- P2: Voice verification (TFLite)

## Test coverage
- Backend: 33 tests, 100% pass — `/app/backend/tests/backend_test.py`
- Frontend: smoke-tested via screenshots (login + captcha, super admin overview, platform settings, geo-fence map, employee home + leave balances)
