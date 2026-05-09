# Test Credentials — Payroll & Attendance PWA

## Super Admin (seeded automatically)
- Email: `admin@payroll.app`
- Password: `admin123`
- Role: `super_admin`
- Login URL: `/login`
- After login redirects to: `/admin`

## Employer (created by Super Admin via UI or API)
- Endpoint: `POST /api/admin/employers` with body `{name, admin_email, admin_password, admin_name, address?, phone?}`
- After creation, sign in with `admin_email` / `admin_password` -> redirects to `/employer`

## Employee (created by Employer via UI or API)
- Endpoint: `POST /api/employees` with body `{name, email, password, emp_code, monthly_salary, ...}`
- After creation, employee signs in with `email` / `password` -> redirects to `/me`

## Auth endpoints
- `POST /api/auth/login` — body `{email, password}` -> returns `{access_token, user}`
- `GET /api/auth/me` — returns current user (Bearer token or cookie)
- `POST /api/auth/logout` — clears cookie

## Notes
- Online disbursement (`POST /api/payroll/items/{id}/disburse` with `method: "online"`) is **MOCKED** — returns a fake `MOCK-XXXX` txn_id.
- Email notifications are **MOCKED** (not sent at all in v1).
- Facial verification stores only a SHA256 hash of the captured base64 image — never the raw image.
