# Deploy to Cloudflare Pages + Render + MongoDB Atlas (free-tier)

> **Why hybrid?** Cloudflare Pages is fantastic for the React frontend, but Cloudflare Workers cannot run our FastAPI/Python backend (Mongo driver, APScheduler, bcrypt etc. are Python-only). The standard, **fully free** pattern is: **Cloudflare Pages → Render → MongoDB Atlas**, all connected via Git.

You'll end up with:
- `https://payroll.pages.dev` (or your custom domain) — the PWA
- `https://payroll-api.onrender.com` — the FastAPI backend
- A managed MongoDB cluster on Atlas (Mumbai / `ap-south-1`)

Total time: **~30 min**.

---

## Step 0 — Push the code to GitHub

In the Emergent chat input, click **"Save to GitHub"** to push `/app` to a new GitHub repo. Pick a name like `payroll-pwa`. Note the URL — you'll connect Cloudflare and Render to this repo.

> If you already have a GitHub remote, skip this step.

---

## Step 1 — MongoDB Atlas (database)

1. Go to <https://www.mongodb.com/cloud/atlas/register> and sign up (free).
2. Create a **free M0 cluster** in **AWS · Mumbai (ap-south-1)** (closest to Indian users + matches our Privacy Notice).
3. **Database Access** → *Add new database user*
   - Username: `payroll`
   - Password: click *Autogenerate* → **copy and save it**
   - Built-in role: *Read and write to any database*
4. **Network Access** → *Add IP address* → **Allow access from anywhere** (`0.0.0.0/0`).
   *(Render's IPs aren't static on the free plan; lock this down later when you upgrade.)*
5. **Database → Connect → Drivers → Python (3.11)** → copy the connection string. It looks like:
   ```
   mongodb+srv://payroll:<password>@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority
   ```
   Replace `<password>` with the one you saved.

✅ Save this as `MONGO_URL` for later.

---

## Step 2 — Render (backend / FastAPI)

1. Go to <https://render.com> → **Sign in with GitHub**.
2. **New +** → **Web Service** → connect your `payroll-pwa` repo.
3. Configure the service:

   | Field | Value |
   |---|---|
   | Name | `payroll-api` |
   | Region | **Singapore** (closest free-tier to India) |
   | Branch | `main` |
   | Root Directory | `backend` |
   | Runtime | **Python 3** |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn server:app --host 0.0.0.0 --port $PORT` |
   | Instance Type | **Free** |

4. Scroll to **Environment Variables** and add **all** of these:

   | Key | Value |
   |---|---|
   | `MONGO_URL` | (from Step 1) |
   | `DB_NAME` | `payroll` |
   | `JWT_SECRET` | run `python -c "import secrets; print(secrets.token_hex(32))"` and paste |
   | `JWT_ALGORITHM` | `HS256` |
   | `JWT_EXPIRES_HOURS` | `12` |
   | `ADMIN_EMAIL` | `admin@yourdomain.com` |
   | `ADMIN_PASSWORD` | (your strong password) |
   | `CORS_ORIGINS` | `https://payroll.pages.dev,https://your-custom-domain.com,https://localhost,capacitor://localhost` *(last two are required so the Android + iOS Capacitor apps can call the API — the WebView's origin is `https://localhost` on Android and `capacitor://localhost` on iOS)* |
   | `APP_BASE_URL` | `https://payroll-api.onrender.com` |
   | `TIMEZONE` | `Asia/Kolkata` |

   Optional (skip for now if you don't have keys yet — features just stay off):

   | Key | Used for |
   |---|---|
   | `RESEND_API_KEY` | Welcome emails |
   | `SENDER_EMAIL` | `noreply@noratech.in` (must match your verified Resend domain) |
   | `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_FROM` | WhatsApp alerts |

5. Click **Create Web Service**. First build takes ~5 min.

6. When it's live, open the Render URL (e.g. `https://payroll-api.onrender.com/api/health`) — you should see:
   ```json
   {"ok": true, "ts": "..."}
   ```

✅ Save this URL as `REACT_APP_BACKEND_URL` for the next step.

> **Free-tier gotcha**: Render free spins down after 15 min idle. First request after sleep takes ~30 s. To keep it warm: ping `/api/health` from a free **UptimeRobot** monitor every 5 min, or upgrade to the $7/mo Starter plan.

---

## Step 3 — Cloudflare Pages (frontend / React)

1. Go to <https://dash.cloudflare.com> → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**.
2. Authorize Cloudflare to access your GitHub, pick the `payroll-pwa` repo.
3. Configure the build:

   | Field | Value |
   |---|---|
   | Project name | `payroll` (gives you `payroll.pages.dev`) |
   | Production branch | `main` |
   | Framework preset | **Create React App** |
   | Build command | `yarn install && yarn build` |
   | Build output directory | `build` |
   | Root directory | `frontend` |

4. **Environment variables (Production)**:

   | Key | Value |
   |---|---|
   | `REACT_APP_BACKEND_URL` | `https://payroll-api.onrender.com` *(Render URL from Step 2)* |
   | `NODE_VERSION` | `20` |
   | `CI` | `false` *(prevents the build failing on warnings)* |

5. **Save and Deploy**. First build takes ~3 min. When done, your PWA is live at `https://payroll.pages.dev`.

---

## Step 4 — Wire CORS so they can talk

Go back to **Render → payroll-api → Environment** and update:

```
CORS_ORIGINS = https://payroll.pages.dev,https://your-custom-domain.com
```

Click **Save Changes** — Render auto-redeploys.

Open `https://payroll.pages.dev`, log in with your `ADMIN_EMAIL` / `ADMIN_PASSWORD`. You should land on the Super Admin dashboard. ✅

---

## Step 5 — Custom domain (optional, recommended)

### For the frontend (`app.noratech.in`)
1. **Cloudflare Pages → payroll → Custom domains → Set up a custom domain** → enter `app.noratech.in`.
2. Cloudflare auto-creates the CNAME if your domain is on Cloudflare DNS. Otherwise add a CNAME `app → payroll.pages.dev` at your registrar.

### For the API (`api.noratech.in`)
1. In your DNS panel, add **CNAME** `api → payroll-api.onrender.com` (orange-cloud / proxied **off** in Cloudflare for Render TLS to work).
2. **Render → payroll-api → Settings → Custom Domain** → add `api.noratech.in`. Wait for the "Verified" badge.
3. Update Render env: `APP_BASE_URL = https://api.noratech.in`, `CORS_ORIGINS = https://app.noratech.in`.
4. Update Cloudflare Pages env: `REACT_APP_BACKEND_URL = https://api.noratech.in` → redeploy.

---

## Step 6 — Continuous deployment

You're done — **every `git push` to `main` now redeploys automatically**:

- Frontend changes → Cloudflare Pages rebuilds & invalidates the CDN.
- Backend changes → Render rebuilds & rolls out a new pod.
- Database stays put on Atlas.

---

## Troubleshooting

**Login fails with "Network Error" / CORS error in browser console**
→ `CORS_ORIGINS` on Render doesn't include your Cloudflare Pages URL. Add it (comma-separated) and let Render redeploy.

**Captcha "expired — please refresh" on every login**
→ Frontend and backend disagree on time. Render uses UTC by default; we set `TIMEZONE=Asia/Kolkata` for scheduled jobs only — this should not affect captcha. If it persists, regenerate captcha and check that `JWT_EXPIRES_HOURS` is reasonable.

**MongoDB connection timeout in Render logs**
→ Atlas → Network Access → confirm `0.0.0.0/0` is allowed. The Atlas connection string must include `?retryWrites=true&w=majority`.

**Cold-start: first request after 15 min is slow**
→ Render free tier sleeps. Either upgrade to Starter ($7/mo) or use UptimeRobot to ping `/api/health` every 5 min.

**Frontend build fails with "Treating warnings as errors"**
→ Add env var `CI=false` on Cloudflare Pages and re-deploy.

**APScheduler fires twice / duplicate payroll drafts**
→ Free Render runs one instance, so this is fine. If you ever scale to >1 instance, move scheduled jobs out to a dedicated worker.

---

## Cost summary

| Service | Free tier | Paid (when you outgrow) |
|---|---|---|
| Cloudflare Pages | Unlimited bandwidth, 500 builds/mo | Free forever for our scale |
| Render Web Service | 750 hrs/mo, sleeps after 15 min | $7/mo Starter (always-on) |
| MongoDB Atlas M0 | 512 MB, 100 conns | $9/mo M2 (2 GB) |
| Cloudflare DNS | Free | Free |
| **Total free** | **₹0/mo** | **~₹1,300/mo** when you outgrow |

That's the full pipeline. Push to GitHub once and every change deploys itself.
