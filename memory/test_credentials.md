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
| Employer (NoraTech) | `apoorvchandra01+employer@gmail.com` | `demoadmin123` |
| Employee (Apoorv) | `apoorvchandra01@gmail.com` | `emp123456` |

## Two-step confirmations
- **Delete employer / employee** → must type the entity name to confirm
- **Approve / reject payroll** → must re-enter the employer's password
- **Delete payroll run** → must type `Month YYYY` (e.g. `May 2026`)

## Auth API
- `GET  /api/auth/captcha` → `{ token, a, b, op }` (server keeps the answer)
- `POST /api/auth/login` body: `{ email, password, captcha_token, captcha_answer }` → `{ access_token, user }`
- `GET  /api/auth/me` (Bearer or cookie) → user object
- `POST /api/auth/logout`

## Notes
- **Email**: only the Welcome-on-employee-onboard email is wired (Resend via `RESEND_API_KEY`). Everything else moved to WhatsApp.
- **WhatsApp**: leave-decision and salary-ready notifications. Off until Super Admin → Platform → "Enable WhatsApp notifications" is toggled ON **and** `TWILIO_*` env vars are set.
- **Online disbursement (RazorpayX)**: still **MOCKED** — returns `MOCK-XXXXXXXX` txn id.
- **Backdated attendance**: configurable via Super Admin → Platform → `max_backdate_days` (default 30). Months with approved/disbursed payroll are locked until employer deletes the run.
