# Test Credentials — Payroll & Attendance PWA

## Login flow
- Visit `/login`
- Solve the visual math captcha (server-issued, refreshes every 5 minutes)
- Enter email + password
- Toggle language anytime via the 🌐 button (English / हिन्दी)

## Super Admin (auto-seeded on first boot)
- Email: `admin@payroll.app`
- Password: `admin123` (change `ADMIN_PASSWORD` in `backend/.env` for production)
- After login → `/admin` (Overview · Employers · Platform · Audit)

## Live test users (current preview environment)
| Role | Email | Password |
|---|---|---|
| Super Admin | `admin@payroll.app` | `admin123` |
| Employer (Doodhnathnath — has Payroll + Students) | `apoorvchandra02@gmail.com` | (set via super-admin reset; ask user for current) |

## Two-step confirmations
- **Delete employer / employee** → must type the entity name to confirm
- **Approve / reject payroll** → must re-enter the employer's password
- **Delete payroll run** → must type `Month YYYY` (e.g. `May 2026`)

## Auth API
- `GET  /api/auth/captcha` → `{ token, a, b, op }` (server keeps the answer)
- `POST /api/auth/login` body: `{ email, password, captcha_token, captcha_answer }` → `{ access_token, user }`
- `GET  /api/auth/me` (Bearer or cookie) → user object
- `POST /api/auth/logout`
- `GET  /api/auth/employers` (public) → `[{ id, name }]` — list of tenants accepting signups
- `POST /api/auth/signup` (public) body: `{ tenant_id, name, email, password, phone?, consent, captcha_token, captcha_answer }` → creates a **pending** employee. Login is blocked (403) until employer approves.

## Self-serve onboarding (employer side)
- `GET  /api/employees/pending` (employer) → list of pending signup requests
- `POST /api/employees/{id}/approve` (employer) body: `ApproveSignupRequest { emp_code, monthly_salary, designation?, ... }` → activates the account + sends welcome email
- `POST /api/employees/{id}/reject` (employer) → permanently deletes the request

## Modules / Feature framework (v11+)
- After login, the app fetches `GET /api/me/features` and routes:
  - 0 features → `/launchpad` empty state ("No modules enabled")
  - 1 feature  → straight into that module's landing path (`/me`, `/school`, etc.)
  - 2+ features → `/launchpad` tile picker
- Catalog: **Payroll & Attendance** (`payroll`), **Student Records** (`students`).
- Existing employers default to `enabled_features=["payroll"]`. Super admin grants more from Admin → Employers card → "Manage modules" button. Employer-admin user is auto-widened; employees are NOT (employer grants per-employee from Employees table → grid icon).
- Endpoints:
  - `GET  /api/features` (public catalog)
  - `GET  /api/me/features` (effective features for the logged-in user)
  - `PUT  /api/admin/employers/{tenant_id}/features` body `{codes:[...]}` (super_admin only)
  - `PUT  /api/employees/{employee_user_id}/features` body `{codes:[...]}` (employer only, must be subset of tenant's enabled)

## Students module (v11+)
- Routes: `/api/students` (CRUD), `/api/students/{id}/files/{slot}` (upload/delete), `/api/students/files/{file_id}` (download — Bearer JWT OR signed `?t=<token>`), `/api/students/_sheets/info|configure`.
- File slots (12): `photo, signature, tenth_marksheet, twelfth_marksheet, graduation_marksheet, pg_marksheet, income_certificate, caste_certificate, domicile_certificate, affidavit, aadhaar_front, aadhaar_back`.
- Allowed mimes: JPEG / PNG / WEBP / PDF. 25 MB cap. Auto-compressed via Pillow + pikepdf.
- Aadhaar masked in API responses (`aadhaar_masked: "XXXX XXXX 1234"`).
- Google Sheets sync: requires `GOOGLE_SERVICE_ACCOUNT_JSON_B64` env (set in this preview). Employer must pre-create a spreadsheet, share with `admission-data@vital-petal-497816-b6.iam.gserviceaccount.com` as Editor, then PUT `/api/students/_sheets/configure` with the URL/ID.

## Notes
- **Email**: only the Welcome-on-employee-onboard email is wired (Resend via `RESEND_API_KEY`). Everything else moved to WhatsApp.
- **WhatsApp**: leave-decision and salary-ready notifications. Off until Super Admin → Platform → "Enable WhatsApp notifications" is toggled ON **and** `TWILIO_*` env vars are set.
- **Online disbursement (RazorpayX)**: still **MOCKED** — returns `MOCK-XXXXXXXX` txn id.
- **Backdated attendance**: configurable via Super Admin → Platform → `max_backdate_days` (default 30). Months with approved/disbursed payroll are locked until employer deletes the run.
