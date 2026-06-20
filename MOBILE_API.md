# Mobile Integration Guide

> **Audience**: Any developer (Android native, iOS, React Native, Flutter) building a mobile client against this backend.
> **Last updated**: 2026-06-14 (v17)

## 1. Quick facts

| Item | Value |
|---|---|
| **Base URL (preview)** | `https://pdf-editor-lite.preview.emergentagent.com` |
| **Base URL (prod)** | Set on deploy — `process.env.REACT_APP_BACKEND_URL` / `settings.APP_BASE_URL` |
| **API prefix** | `/api/*` (all routes) |
| **Auth** | JWT Bearer in `Authorization: Bearer <token>` header. Token also accepted as `access_token` cookie. |
| **Token TTL** | 30 days, refreshable. Stateless — no server-side session store. |
| **Content-Type** | `application/json` for everything except file upload (`multipart/form-data`). |
| **OpenAPI spec** | `GET /api/openapi.json` (FastAPI-generated, regenerated on every deploy). |
| **CORS** | Allow-list of registered origins; for native apps (no origin), CORS is bypassed. |

## 2. Authentication flow

```
┌────────────────────────────────────────────────────────────────────┐
│ 1. GET  /api/auth/captcha                                          │
│    → { token, a, b, op }   ←  e.g. {token:"xyz", a:7, b:3, op:"+"} │
│                                                                    │
│ 2. POST /api/auth/login                                            │
│    body: { email, password, captcha_token, captcha_answer }        │
│    → { access_token, user }                                        │
│    (captcha_answer is the numeric result of `a op b`)              │
│                                                                    │
│ 3. Store access_token in secure-storage (Keychain / Keystore).     │
│                                                                    │
│ 4. Every subsequent call:                                          │
│    headers: { Authorization: "Bearer <access_token>" }             │
│                                                                    │
│ 5. GET /api/auth/me → returns the current user object              │
│ 6. POST /api/auth/logout → server-side captcha invalidation        │
└────────────────────────────────────────────────────────────────────┘
```

**Captcha tip**: the captcha is a simple "what's 7 + 3?" puzzle. Required for **login + signup** only — not for any subsequent call.

**Error envelope**: every 4xx/5xx returns `{ "detail": "human-readable error message" }`. Show `detail` directly to the user; the wording is already user-friendly.

## 3. Module-permission model

Every user has a list of **enabled feature codes** ("modules"). The mobile UI must respect this list.

```
GET /api/me/features
→ {
    role: "employer" | "employee" | "super_admin",
    features: [
      { code: "payroll",  name: "Payroll & Attendance", icon: "Wallet",         landing_path: "/employer" },
      { code: "students", name: "Student Records",      icon: "GraduationCap",  landing_path: "/school" }
    ]
  }
```

After login:
- **0 features** → show "No modules enabled, contact admin" empty state.
- **1 feature** → land straight on that module's home.
- **2+ features** → land on payroll if present, expose a kebab/3-dot menu to switch.

## 4. Endpoint inventory (v17)

### Auth
| Method | Path | Notes |
|---|---|---|
| GET | `/api/auth/captcha` | Public. Token TTL ~5 min. |
| POST | `/api/auth/login` | Body: `{email, password, captcha_token, captcha_answer}` |
| POST | `/api/auth/signup` | Body: `{name, email, password, signup_code}` — employer invite code |
| GET | `/api/auth/me` | Returns logged-in user; refresh-friendly. |
| POST | `/api/auth/logout` | Optional — client just discards the token. |
| POST | `/api/auth/forgot-password` | Email reset link. |

### Payroll module (feature: `payroll`)
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/api/attendance/today` | employee | `{date, marked, record}` |
| POST | `/api/attendance/mark` | employee | Body: `{method, type, latitude, longitude, face_capture_id, overwrite}` |
| GET | `/api/attendance/history?month=&year=` | employee | Array of records. |
| GET | `/api/attendance/locations/me` | employee | Pin map points (privacy-gated). |
| GET | `/api/leave/balances` | employee | |
| GET | `/api/leave/applications` | employee | |
| POST | `/api/leave/apply` | employee | Body: `{leave_type, from_date, to_date, half_day, reason}` |
| GET | `/api/payroll/my` | employee | Past salary slips. |
| GET | `/api/payroll/items/{id}/slip` | employee | PDF download (binary). |
| GET | `/api/employees` | employer | Roster. |
| POST | `/api/employees` | employer | Create employee. |
| GET | `/api/employer/settings` | employer | Tenant config. |
| POST | `/api/payroll/runs` | employer | Generate monthly draft. |

### Students module (feature: `students`)
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/api/students?q=&skip=&limit=` | any with feature | Paginated; q filters by name/father/mobile/email. |
| POST | `/api/students` | any with feature | Body matches `StudentIn` (see OpenAPI). Returns `{id, serial_no, aadhaar_masked, ...}`. Raw `aadhaar` never returned. |
| GET | `/api/students/{id}` | any with feature | Owner check: employee only sees own. |
| PATCH | `/api/students/{id}` | any with feature | Same shape as POST. |
| DELETE | `/api/students/{id}` | any with feature | Soft-delete. |
| POST | `/api/students/{id}/files/{slot}` | any with feature | multipart upload. Slots: `photo, signature, tenth_marksheet, twelfth_marksheet, graduation_marksheet, pg_marksheet, income_certificate, caste_certificate, domicile_certificate, affidavit, aadhaar_front, aadhaar_back`. Max 25 MB. Auto-compressed. |
| GET | `/api/students/files/{file_id}?t=<token>` | any | Streamed file. `t=` is HMAC-signed (30d TTL); embed in Sheets cells. |
| DELETE | `/api/students/{id}/files/{slot}` | any with feature | Removes from GridFS. |
| GET | `/api/students/_sheets/info` | employer | `{configured, service_account_email, master_sheet_id, master_sheet_url}` |
| PUT | `/api/students/_sheets/configure` | employer | Body: `{url_or_id}`. Probes write access, then binds. |
| POST | `/api/students/_sheets/resync` | employer | Returns `{job_id, total}`. Background worker. |
| GET | `/api/students/_sheets/resync/{job_id}` | employer | Poll status: `{status, progress, total, errors, more_errors}`. |

### Super Admin
| Method | Path | Notes |
|---|---|---|
| GET | `/api/admin/employers` | All employers + `enabled_features`. |
| POST | `/api/admin/employers` | Create new employer + employer-admin user. |
| GET | `/api/admin/employers/{id}/employees` | Drill-down — every employee + their feature_permissions. |
| PUT | `/api/admin/employers/{id}/features` | Body: `{codes: ["payroll", "students"]}`. Cascade-revokes employees. |
| DELETE | `/api/admin/employers/{id}` | Hard-delete (employer + per-tenant DB). |
| PUT | `/api/employees/{user_id}/features` | Employer grants per-employee feature subset. |
| GET | `/api/admin/audit?limit=` | Last N events across all employers. |

### Privacy (DPDP compliance)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/me/privacy` | Consents + erasure status. |
| PUT | `/api/me/privacy/consents` | Body: `{consents: {data_processing, face_capture, geo_location, whatsapp_email}}` |
| POST | `/api/me/privacy/erasure` | Schedule account deletion. |
| POST | `/api/me/privacy/password` | Change own password. |

## 5. Native Android specifics

| Concern | What to do |
|---|---|
| **Location** | Request `ACCESS_FINE_LOCATION` at runtime (Android 6+). Use `LocationManager` or Capacitor's `@capacitor/geolocation`. Send `latitude` + `longitude` floats to `/api/attendance/mark`. |
| **Camera** | Request `CAMERA` at runtime. Use `Camera` plugin or native `Intent.ACTION_IMAGE_CAPTURE`. Returns a JPEG byte stream — upload to `/api/students/{id}/files/photo`. |
| **Face liveness** | Currently web-only via `face-api.js`. For native, integrate **ML Kit Face Detection** (free, on-device) and POST the capture binary to `/api/auth/face-liveness/verify` (TODO: stub endpoint). |
| **Offline attendance** | Backend already supports `overwrite=true` for replay. Mobile should queue marks in a local SQLite/Room table and flush on reconnect — exactly mirrors the web IndexedDB queue. |
| **Push notifications** | Currently uses email/WhatsApp only. Add `@capacitor/push-notifications` + FCM (Firebase) for native push — endpoint TODO: `POST /api/me/push-token`. |
| **Secure storage** | Use `EncryptedSharedPreferences` (Android Keystore-backed) for the JWT, NOT plain SharedPrefs. |

## 6. Build the Capacitor APK

### Inside this container (verified working)

A pre-built debug APK already lives at **`/app/dist/payroll-debug.apk`**
(7.6 MB, package `com.norratech.payrollstudents`, label "Payroll & Students",
compiled against SDK 35).

To rebuild from source:

```bash
# One-time per fresh container (installs JDK 17 + 21, Android SDK 35,
# qemu-x86_64-static + ARM-emulation wrappers — see comments in the script).
/app/scripts/setup-android-sdk.sh

# Every subsequent build:
/app/scripts/build-android-apk.sh
# → /app/dist/payroll-debug.apk
```

The setup script handles the aarch64 host problem: Google ships only x86_64
build-tools / platform-tools, so each x86_64 ELF binary is renamed to
`<name>.x86_64` and replaced with a shell wrapper that exec's it under
`qemu-x86_64-static`. Gradle therefore runs unchanged.

### Inside Android Studio (recommended for normal dev)

```bash
cd /app/frontend
yarn build                          # CRA production build → ./build
npx cap sync android                # copy build → android/app/src/main/assets/public

cd android
./gradlew assembleDebug             # debug APK: app/build/outputs/apk/debug/app-debug.apk
./gradlew bundleRelease             # release .aab for Play Store
```

For release, you'll need a keystore (`keytool -genkey`) and a signing config in `android/app/build.gradle`. Capacitor's docs walk through this in detail.

## 7. Versioning the API

The backend currently exposes a single, unversioned `/api`. For mobile longevity, freeze a versioned snapshot:

```
GET /api/openapi.json   ← regenerated on every deploy
```

A future v2 will expose `/api/v2/*` alongside `/api/*` so old mobile builds keep working.

## 8. Error codes you must handle gracefully

| Status | Meaning | Mobile UX |
|---|---|---|
| 401 | Token expired or invalid | Force re-login screen. |
| 403 | Module not enabled or wrong role | Show "Contact admin to enable this module". |
| 409 | Conflict (e.g. resync in flight) | Show inline message — don't auto-retry. |
| 413 | File too large (>25MB) | Compress client-side or refuse. |
| 415 | Unsupported file type | Allow only JPEG/PNG/WEBP/PDF in the picker. |
| 429 | Rate limited (rare) | Backoff + retry. |
| 5xx | Server error | Toast + offline queue. |

## 9. Contact

- Backend issues / new endpoints → open a ticket in this repo with the `mobile` label.
- Service account email for Google Sheets integration → `admission-data@vital-petal-497816-b6.iam.gserviceaccount.com` (already provisioned).
