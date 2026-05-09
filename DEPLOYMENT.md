# Production deployment guide

This guide walks you through deploying the Payroll & Attendance platform to production. Three paths are documented; pick the one that matches your operations preference.

---

## Path A — Single VPS with Docker Compose (simplest, $5–10/mo)

**Best for:** small businesses, internal tools, MVP launches.

### 1. Provision a server
- DigitalOcean / Hetzner / Linode 1–2 GB droplet, Ubuntu 22.04 LTS
- Install Docker + Compose:
  ```bash
  curl -fsSL https://get.docker.com | sh
  ```
- Open ports 80 and 443 in your firewall.

### 2. Clone & configure
```bash
git clone <your-repo-url> /opt/payroll && cd /opt/payroll
cp backend/.env.example backend/.env
nano backend/.env
```
Required edits in `backend/.env`:
- `JWT_SECRET` — generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- `ADMIN_PASSWORD` — your initial Super Admin password
- `APP_BASE_URL` — your public URL (https)
- `RESEND_API_KEY` + `SENDER_EMAIL` — for welcome emails
- `TWILIO_*` — only needed if you'll use WhatsApp

### 3. Set the public-facing API URL
Export it before running compose so the React build bakes the right URL:
```bash
export REACT_APP_BACKEND_URL=https://payroll.your-domain.com
docker compose up -d --build
```

### 4. Front with Caddy (auto-TLS)
```bash
apt install -y caddy
cat <<'CADDY' > /etc/caddy/Caddyfile
payroll.your-domain.com {
  reverse_proxy /api/* localhost:8001
  reverse_proxy localhost:3000
}
CADDY
systemctl restart caddy
```
DNS: point `payroll.your-domain.com` A-record to your server IP. Caddy issues TLS automatically.

### 5. Backups
Add a daily Mongo dump cron:
```bash
0 3 * * * docker exec $(docker ps -qf name=mongo) mongodump --archive=/data/db/backup-$(date +\%F).archive
```

---

## Path B — Free-tier split (Render + Cloudflare Pages + Atlas)

**Best for:** zero-cost MVP launches.

### 1. Database — MongoDB Atlas (free 512 MB)
1. https://cloud.mongodb.com → New Project → Build Database (M0 free tier)
2. Database Access → Add user `payroll` with a password
3. Network Access → Add IP `0.0.0.0/0` (or limit to Render egress IPs)
4. Copy the connection string: `mongodb+srv://payroll:<pwd>@cluster0.xxxxx.mongodb.net`

### 2. Backend — Render
1. https://render.com → New Web Service → connect your GitHub repo
2. Root directory: `backend`, Environment: `Docker`
3. Plan: Free
4. Environment variables (paste from your `backend/.env`):
   - `MONGO_URL` = the Atlas SRV string from step 1
   - `DB_NAME` = `payroll_db`
   - `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `APP_BASE_URL`
   - `RESEND_API_KEY`, `SENDER_EMAIL`
   - `TWILIO_*` (optional)
   - `CORS_ORIGINS` = `https://your-frontend.pages.dev`
5. Render gives you a URL like `https://payroll-api.onrender.com`. Save it.

### 3. Frontend — Cloudflare Pages
1. https://pages.cloudflare.com → Create project → connect GitHub repo
2. Build settings:
   - Framework: **Create React App**
   - Build command: `yarn build`
   - Output directory: `frontend/build`
   - Root directory: `frontend`
3. Environment variable:
   - `REACT_APP_BACKEND_URL` = the Render URL from step 2
4. Save & deploy. CF Pages gives you `https://your-project.pages.dev`.

### 4. Custom domain
Cloudflare Pages → Custom domains → Add your domain → CF auto-handles DNS + TLS.

> **Note:** Render free instances sleep after 15 min of inactivity. First request after sleep takes ~30 s. Upgrade to the $7/mo "Starter" tier to keep it warm.

---

## Path C — Kubernetes (large scale)

**Best for:** organisations with existing k8s expertise.

The Dockerfiles in `backend/` and `frontend/` are k8s-ready. A minimal deployment:

```yaml
# Save as payroll.yaml; kubectl apply -f payroll.yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: payroll-backend }
spec:
  replicas: 2
  selector: { matchLabels: { app: payroll-backend } }
  template:
    metadata: { labels: { app: payroll-backend } }
    spec:
      containers:
        - name: backend
          image: ghcr.io/<you>/payroll-backend:latest
          ports: [{ containerPort: 8001 }]
          envFrom: [{ secretRef: { name: payroll-secrets } }]
          readinessProbe: { httpGet: { path: /api/health, port: 8001 } }
---
apiVersion: v1
kind: Service
metadata: { name: payroll-backend }
spec:
  selector: { app: payroll-backend }
  ports: [{ port: 80, targetPort: 8001 }]
```

Use a managed Mongo (Atlas, AWS DocumentDB) and front with an Ingress that routes `/api` to backend, `/` to frontend.

---

## Post-deploy checklist

- [ ] First-time login as `admin@payroll.app` → change password
- [ ] Super Admin → **Platform** → Enable WhatsApp (only if Twilio creds set) and set `max_backdate_days`
- [ ] Onboard your first employer
- [ ] Login as employer → Settings → configure geo-fence, working days, leave types
- [ ] Add your first employee — they get a welcome email with credentials
- [ ] Verify Resend domain (`https://resend.com/domains`) before going live
- [ ] (Optional) Verify Twilio production number — for sandbox, recipients must `join <keyword>` first

---

## Updating the deployment

```bash
cd /opt/payroll
git pull
docker compose up -d --build
```

DB schema is **forward-compatible** — Mongo indexes are created idempotently on every boot in `app/db.py:ensure_indexes()`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `502 Bad Gateway` from frontend | Render free service asleep | Wait ~30 s for first request OR upgrade tier |
| `Captcha expired` on login | Server clock skew or 5-min TTL | Click refresh on captcha; sync server time with NTP |
| Welcome email not received | Sender domain unverified on Resend | https://resend.com/domains → Verify DNS |
| WhatsApp message never arrives | Recipient hasn't opted into sandbox | Recipient must send `join <keyword>` to `+14155238886` once |
| `Outside geo-fence (... m away)` | Employee moving outside the radius | Loosen radius in Employer → Settings → Geo-fence |
| Source-map warnings about `face-api.js/src/...ts` | Harmless — face-api ships .ts that aren't bundled | Ignore |

---

## Security hardening (recommended for production)

1. Rotate `JWT_SECRET` quarterly (forces re-login).
2. Set `CORS_ORIGINS` to your exact frontend host (not `*`).
3. Enable Atlas IP allowlist (limit to Render/Render egress).
4. Add a CDN (Cloudflare orange-cloud) in front of both endpoints.
5. Backups: nightly Atlas point-in-time backups (M10+) or local `mongodump`.
6. Audit log review: Super Admin → Audit weekly.
