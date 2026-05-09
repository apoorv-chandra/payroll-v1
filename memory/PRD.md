# Payroll & Attendance PWA — PRD

## Original problem statement
> "read the pdf provided and ask for any changes in required in pdf. Use the fastest services but free tier. Use cloud flare pages, render etc if required. Let me know."

User shared a comprehensive **Payroll Build Guide v2** PDF: a multi-tenant payroll & attendance platform with super-admin / employer / employee roles, 12 attendance configurations, geo-fencing, facial+voice verification, leave management, 26-day payroll, RazorpayX disbursement, salary slip PDFs, DPDP-compliance, etc.

## User choices (final)
- **No changes** to PDF spec
- **Mobile-first PWA** (Web MVP, 100% mobile-friendly)
- Stack: **React + FastAPI + MongoDB** (Emergent default)
- **Mobile native apps** (Expo): out of scope for this environment
- **Integrations**: facial via browser camera (on-device), email & RazorpayX → **MOCKED** (no keys provided)

## Architecture
- **Backend** `/app/backend/server.py` — FastAPI + Motor (async Mongo)
  - JWT auth (cookie + Bearer), bcrypt hashing
  - Multi-tenant scoping: every collection has `tenant_id` (super admin sees all)
  - Role-based dependencies: `super_admin`, `employer`, `employee` + elevated roles `accountant`, `principal`, `cashier`
  - Salary slip PDF generation via ReportLab with Indian comma formatting (₹1,00,000)
- **Frontend** `/app/frontend/src` — React 19 + Tailwind, mobile-first PWA
  - Auth context + protected routes per role
  - Three role-scoped apps: `AdminApp`, `EmployerApp`, `EmployeeApp`
  - Bottom-tab navigation on mobile, desktop sidebar fallback
  - PWA manifest + service worker + safe-area padding
  - Camera viewfinder + geolocation for attendance marking

## User personas
- **Super Admin** — operator. Onboards employers, sees platform stats & audit log.
- **Employer** — workspace admin. Manages employees, attendance config, leave types, geo-fence, approves leaves & payroll, downloads slips.
- **Employee** — end user. Marks attendance (camera + GPS), applies leave, views balances, downloads own salary slips.
- **Accountant / Principal / Cashier** — elevated employee roles for payroll generation, leave approval, cash disbursement.

## Implemented (May 9, 2026)
**Backend (33/33 tests pass)**
- `/api/auth/login`, `/auth/me`, `/auth/logout`
- Super Admin: `POST/GET/DELETE /api/admin/employers`, `/api/admin/audit`, `/api/admin/stats`
- Tenant settings: `GET/PUT /api/tenant/settings` (leave types, geo-fence, working days)
- Employees: full CRUD `/api/employees` (auto-creates user account, seeds pro-rated leave balances)
- Attendance: `/api/attendance/mark`, `/today`, `/history` with geo-fence enforcement (haversine)
- Leave: `/api/leave/balances`, `/apply`, `/applications`, `/applications/{id}/decision`
- Payroll: `/api/payroll/generate` (26-day formula), `/runs`, `/runs/{id}`, `/runs/{id}/approve`, `/items/{id}/disburse` (cash/online MOCKED), `/items/{id}/slip` (PDF), `/my`
- Cross-tenant isolation verified by tests
- Audit log for all writes

**Frontend**
- Login screen with serif heading, demo creds visible
- Super Admin dashboard: stats tiles + employers list + add modal + audit log
- Employer dashboard: overview, employees CRUD, leave inbox with approve/reject, payroll runs (generate/approve/disburse/PDF), settings (attendance config, geo-fence, leave types editor)
- Employee dashboard: today's status + check-in/out with camera+GPS, leave balances, history, apply leave, leave history, salary slip downloads
- PWA: manifest, service worker, viewport-fit cover, safe-area padding
- Indian comma formatting (en-IN) throughout

## Mocked / Deferred
- **MOCKED**: Online payouts (RazorpayX) — returns `MOCK-XXXXXXXX` txn id
- **MOCKED**: Email notifications (no SMTP wired)
- **Deferred**: Voice verification (TFLite), offline attendance queue sync, Hindi i18n, raw map UI for geofence (we expose lat/lng/radius inputs + "use my location" button), DPDP consent screens

## Backlog (P1 → P2)
- P1: Real RazorpayX integration (needs `RAZORPAYX_KEY_ID` + `RAZORPAYX_KEY_SECRET` from user)
- P1: Resend / SendGrid for leave & payroll notifications
- P1: face-api.js liveness check (currently captured but only hashed)
- P1: Visual map for geofence editor (MapLibre GL + OSM)
- P2: Hindi translations + RTL scaffold
- P2: Bulk employee import (CSV)
- P2: Offline queue sync for attendance (IndexedDB + service-worker background sync)
- P2: DPDP consent screens & data export/erasure flows
- P2: Expo / React Native shell (out of scope on Emergent env)

## Test coverage
- Backend: 33 tests, 100% pass — see `/app/backend/tests/backend_test.py`
- Frontend: smoke-tested via screenshots (login, super admin overview, employers list)
