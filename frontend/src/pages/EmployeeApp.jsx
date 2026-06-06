import React, { useEffect, useRef, useState } from "react";
import { Routes, Route, Navigate, useNavigate } from "react-router-dom";
import Shell from "../components/Shell";
import { Button, Card, Input, Select, PageHeader, Empty, Modal, Badge, StatTile, Spinner } from "../components/ui/Primitives";
import { api, fmtErr, fmtDate, fmtINR, fmtTime, monthName } from "../lib/api";
import { Camera, MapPin, LogIn, LogOut as LogOutIcon, Calendar, Clock, ScrollText, Download, Plus, Home, History, Shield, WifiOff, CloudUpload, Trash2, ChevronDown, ChevronUp, Send, Check, X, Banknote, Calculator } from "lucide-react";
import FaceLiveness from "../components/FaceLiveness";
import ConsentGate from "../components/ConsentGate";
import PrivacyNotice from "../components/PrivacyNotice";
import PinMap from "../components/PinMap";
import { enqueue } from "../lib/offlineQueue";
import useOnline from "../lib/useOnline";
import { useAuth } from "../contexts/AuthContext";
import useConfirm from "../lib/useConfirm";
import { requestGeoPermission, getGeoPermissionState } from "../lib/permissions";

const BASE_NAV = [
  { id: "home", to: "/me", end: true, label: "Home", icon: Home },
  { id: "history", to: "/me/history", label: "History", icon: History },
  { id: "leaves", to: "/me/leaves", label: "Leaves", icon: Calendar },
  { id: "slips", to: "/me/slips", label: "Salary", icon: ScrollText },
  { id: "privacy", to: "/me/privacy", label: "Privacy", icon: Shield },
];
const ACCOUNTANT_TAB = { id: "payroll", to: "/me/payroll", label: "Payroll", icon: Calculator };

export default function EmployeeApp() {
  const { user } = useAuth();
  const isAccountant = (user?.elevated_roles || []).includes("accountant");
  const nav = isAccountant ? [...BASE_NAV, ACCOUNTANT_TAB] : BASE_NAV;
  return (
    <ConsentGate>
      <Shell nav={nav}>
        <OfflineBanner />
        <Routes>
          <Route index element={<HomeScreen />} />
          <Route path="history" element={<HistoryScreen />} />
          <Route path="leaves" element={<LeavesScreen />} />
          <Route path="slips" element={<SlipsScreen />} />
          <Route path="privacy" element={<PrivacyScreen />} />
          {isAccountant && <Route path="payroll" element={<AccountantPayroll />} />}
          {isAccountant && <Route path="payroll/:runId" element={<AccountantPayrollRun />} />}
          <Route path="*" element={<Navigate to="/me" replace />} />
        </Routes>
      </Shell>
    </ConsentGate>
  );
}

function OfflineBanner() {
  const { online, queued, needsAuth, drain } = useOnline();
  if (online && queued === 0 && !needsAuth) return null;
  return (
    <div
      data-testid="offline-banner"
      className={`fixed top-14 inset-x-0 z-30 flex items-center justify-center gap-2 text-sm py-2 ${needsAuth ? "bg-red-50 text-red-800 border-b border-red-200" : online ? "bg-amber-50 text-amber-800 border-b border-amber-200" : "bg-gray-900 text-white"}`}
    >
      {needsAuth ? (
        <>
          <Shield className="h-4 w-4" />
          <span data-testid="needs-auth-banner">
            Session expired — sign in again to sync {queued} queued mark{queued === 1 ? "" : "s"}.
          </span>
        </>
      ) : online ? (
        <>
          <CloudUpload className="h-4 w-4" />
          <span>{queued} attendance mark{queued === 1 ? "" : "s"} queued — syncing…</span>
          <button onClick={drain} className="underline" data-testid="retry-drain-btn">Retry now</button>
        </>
      ) : (
        <>
          <WifiOff className="h-4 w-4" />
          <span>Offline — attendance marks will queue and sync when you reconnect.</span>
        </>
      )}
    </div>
  );
}

function PrivacyScreen() {
  const [data, setData] = useState(null);
  const [requiresFacial, setRequiresFacial] = useState(false);
  const [showNotice, setShowNotice] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = async () => {
    try {
      const [p, cfg] = await Promise.all([
        api.get("/me/privacy"),
        api.get("/attendance/config").catch(() => ({ data: { requires_facial: false } })),
      ]);
      setData(p.data);
      setRequiresFacial(!!cfg.data?.requires_facial);
    } catch { setData({}); }
  };
  useEffect(() => { load(); }, []);

  const update = async (key, value) => {
    setBusy(true); setMsg("");
    try {
      // Persist the consent FIRST — never block the toggle on the browser
      // permission, because browsers don't expose a way to deep-link into OS
      // location settings, and a stale "denied" state would silently lock
      // the toggle. Saving consent first matches the user's mental model:
      // "ON means I'm willing to share". The browser/OS permission is a
      // separate layer we surface below.
      const next = { ...data.consents, [key]: value };
      await api.put("/me/privacy/consents", { consents: next });
      await load();
      setMsg("Saved.");
      setTimeout(() => setMsg(""), 1800);

      // After saving, try to obtain the browser permission so the first
      // check-in already has it. If denied / blocked / OS off, surface a
      // clear hint — but keep the consent ON.
      if (key === "geo_location" && value === true) {
        const ok = await requestGeoPermission();
        if (!ok) {
          setMsg(
            "Saved. Your browser couldn't access device location — turn on Location in your phone/browser settings, then try a check-in."
          );
        }
      }
    } catch (e) {
      setMsg(fmtErr(e));
    } finally { setBusy(false); }
  };

  const exportData = async () => {
    const res = await api.get("/me/data-export", { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a"); a.href = url; a.download = `my-data-${Date.now()}.json`; a.click(); URL.revokeObjectURL(url);
  };

  const requestErasure = async () => {
    if (!window.confirm("This schedules your account deletion in 30 days. You can cancel anytime before then. Proceed?")) return;
    try { await api.post("/me/erasure-request"); load(); }
    catch (e) { setMsg(fmtErr(e)); }
  };
  const cancelErasure = async () => {
    await api.delete("/me/erasure-request"); load();
  };

  if (!data) return <Spinner />;
  const c = data.consents || {};
  return (
    <div>
      <PrivacyNotice open={showNotice} onClose={() => setShowNotice(false)} />
      <PageHeader title="Privacy & data"
        subtitle="Your DPDP rights — view, export and delete." />
      <div className="space-y-4">
        <Card>
          <h3 className="font-semibold text-ink mb-3">Consents</h3>
          <ul className="divide-y divide-gray-100">
            {[
              ...(requiresFacial ? [["face_capture", "Face capture during attendance"]] : []),
              ["geo_location", "Location sharing during attendance"],
              ["whatsapp_email", "Notifications by WhatsApp / Email"],
            ].map(([k, label]) => (
              <li key={k} className="py-3 flex items-center justify-between">
                <span className="text-sm">{label}</span>
                <button
                  onClick={() => update(k, !c[k])}
                  disabled={busy}
                  className={`h-9 px-4 rounded-full text-sm font-medium ${c[k] ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-700"}`}
                  data-testid={`toggle-${k}`}
                >
                  {c[k] ? "Granted" : "Withdrawn"}
                </button>
              </li>
            ))}
          </ul>
          {/* Browser/device permission status for location — only meaningful
              when the user has agreed to share location. */}
          {c.geo_location && <GeoPermissionStatusRow />}
          <div className="mt-3 text-xs text-gray-500">
            <button className="text-blue-600 underline" onClick={() => setShowNotice(true)} data-testid="open-privacy-link">Read the full privacy notice</button>
          </div>
        </Card>

        <Card>
          <h3 className="font-semibold text-ink mb-1">Export my data</h3>
          <p className="text-sm text-gray-500 mb-3">Download everything we hold about you as a JSON file.</p>
          <Button variant="secondary" onClick={exportData} data-testid="export-data"><Download className="h-4 w-4" />Download</Button>
        </Card>

        <MyLocationsCard locationConsent={!!c.geo_location} />

        <ChangePasswordCard />

        <Card>
          <h3 className="font-semibold text-ink mb-1">Delete my account</h3>
          {data.erasure_request ? (
            <>
              <p className="text-sm text-gray-700 mb-3">
                Your account will be deleted on <b>{fmtDate(data.erasure_request.scheduled_for)}</b>.
              </p>
              <Button variant="secondary" onClick={cancelErasure} data-testid="cancel-erasure">Cancel deletion</Button>
            </>
          ) : (
            <>
              <p className="text-sm text-gray-500 mb-3">After a 30-day notice, your account and all linked data are permanently deleted.</p>
              <Button variant="danger" onClick={requestErasure} data-testid="request-erasure"><Trash2 className="h-4 w-4" />Request deletion</Button>
            </>
          )}
        </Card>

        {msg && <div className="text-xs text-gray-700 bg-gray-50 border border-gray-200 rounded-md px-3 py-2 inline-block">{msg}</div>}
      </div>
    </div>
  );
}

function GeoPermissionStatusRow() {
  const [state, setState] = useState("unknown");
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState("");

  const refresh = async () => setState(await getGeoPermissionState());

  useEffect(() => {
    let live = true;
    (async () => {
      const s = await getGeoPermissionState();
      if (live) setState(s);
    })();
    return () => { live = false; };
  }, []);

  const test = async () => {
    setBusy(true); setHint("");
    const ok = await requestGeoPermission();
    setBusy(false);
    if (ok) {
      setHint("Location access is working.");
    } else if (state === "denied") {
      setHint("Your browser has blocked location for this site. Open browser site-settings (lock icon in the address bar) → Permissions → Location → Allow, then reload.");
    } else {
      setHint("Couldn't read location. Make sure phone Location/GPS is ON, then try again.");
    }
    refresh();
  };

  const tone =
    state === "granted" ? "text-green-700 bg-green-50 border-green-100"
    : state === "denied" ? "text-red-700 bg-red-50 border-red-100"
    : state === "unsupported" ? "text-gray-600 bg-gray-50 border-gray-100"
    : "text-amber-800 bg-amber-50 border-amber-100";

  const label =
    state === "granted" ? "Browser permission: Granted"
    : state === "denied" ? "Browser permission: Blocked"
    : state === "prompt" ? "Browser permission: Not asked yet"
    : state === "unsupported" ? "Geolocation not supported on this device"
    : "Browser permission: Unknown";

  return (
    <div className={`mt-3 rounded-md border px-3 py-2 text-xs ${tone}`} data-testid="geo-permission-status">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium" data-testid="geo-permission-label">{label}</span>
        <button
          onClick={test}
          disabled={busy || state === "unsupported"}
          className="h-8 px-3 rounded-md text-xs font-medium bg-white border border-current/30 hover:bg-white/70 disabled:opacity-50"
          data-testid="test-location-btn"
        >
          {busy ? "Checking…" : "Test location"}
        </button>
      </div>
      {hint && <div className="mt-2 text-[11px] opacity-90" data-testid="geo-permission-hint">{hint}</div>}
    </div>
  );
}

function MyLocationsCard({ locationConsent = true }) {
  const [items, setItems] = useState(null);
  const [pinFor, setPinFor] = useState(null);   // selected row

  useEffect(() => {
    api.get("/attendance/locations/me")
      .then((r) => setItems(r.data || []))
      .catch(() => setItems([]));
  }, []);

  return (
    <Card data-testid="my-locations-card">
      <h3 className="font-semibold text-ink mb-1 flex items-center gap-2">
        <MapPin className="h-4 w-4 text-blue-600" /> My check-in locations
      </h3>
      <p className="text-sm text-gray-500 mb-3">
        Only days where you allowed location sharing appear here.
      </p>
      {!locationConsent && (
        <div className="text-xs text-amber-800 bg-amber-50 border border-amber-100 rounded-md px-3 py-2 mb-3" data-testid="loc-consent-off-hint">
          Location sharing is currently <b>OFF</b>. Turn the toggle above to <b>Granted</b> to start capturing where you check-in.
        </div>
      )}
      {items === null ? <Spinner /> : items.length === 0 ? (
        <div className="text-sm text-gray-500 bg-gray-50 border border-gray-100 rounded-md px-3 py-3 text-center">
          No locations captured yet.
        </div>
      ) : (
        <ul className="divide-y divide-gray-100 -mx-1">
          {items.map((it) => (
            <li key={it.id} className="py-2.5 px-1 flex items-center gap-3" data-testid={`loc-row-${it.date}`}>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-ink">{fmtDate(it.date)}</div>
                <div className="text-xs text-gray-500 tabular">
                  In: {fmtTime(it.check_in_at)} · Out: {it.check_out_at ? fmtTime(it.check_out_at) : "—"}
                </div>
              </div>
              <button
                onClick={() => setPinFor(it)}
                className="h-9 px-3 rounded-md text-xs font-medium bg-blue-50 text-blue-700 hover:bg-blue-100 inline-flex items-center gap-1"
                data-testid={`map-it-${it.date}`}
              >
                <MapPin className="h-3.5 w-3.5" /> Map it
              </button>
            </li>
          ))}
        </ul>
      )}

      {pinFor && (
        <Modal
          open
          onClose={() => setPinFor(null)}
          title={`${fmtDate(pinFor.date)} — Location`}
          footer={<Button variant="secondary" onClick={() => setPinFor(null)}>Close</Button>}
        >
          <PinMap
            height={360}
            pins={[
              ...(pinFor.check_in_lat != null ? [{ lat: pinFor.check_in_lat, lng: pinFor.check_in_lng, color: "#10B981", label: `Check-in · ${fmtTime(pinFor.check_in_at)}` }] : []),
              ...(pinFor.check_out_lat != null ? [{ lat: pinFor.check_out_lat, lng: pinFor.check_out_lng, color: "#EF4444", label: `Check-out · ${fmtTime(pinFor.check_out_at)}` }] : []),
            ]}
          />
        </Modal>
      )}
    </Card>
  );
}

function ChangePasswordCard() {
  const [cur, setCur] = useState("");
  const [nw, setNw] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState({ kind: "", text: "" });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setMsg({ kind: "", text: "" });
    try {
      await api.post("/auth/change-password", { current_password: cur, new_password: nw });
      setMsg({ kind: "ok", text: "Password updated. Use the new one next time you sign in." });
      setCur(""); setNw("");
    } catch (e2) {
      setMsg({ kind: "err", text: fmtErr(e2) });
    } finally { setBusy(false); }
  };

  return (
    <Card data-testid="change-password-card">
      <h3 className="font-semibold text-ink mb-1">Change my password</h3>
      <p className="text-sm text-gray-500 mb-3">At least 6 characters. Pick something only you know.</p>
      <form onSubmit={submit} className="space-y-2.5">
        <Input
          type="password"
          autoComplete="current-password"
          required
          value={cur}
          onChange={(e) => setCur(e.target.value)}
          placeholder="Current password"
          data-testid="cur-password"
        />
        <Input
          type="password"
          autoComplete="new-password"
          required
          minLength={6}
          value={nw}
          onChange={(e) => setNw(e.target.value)}
          placeholder="New password (min 6 chars)"
          data-testid="new-password"
        />
        <Button type="submit" disabled={busy} data-testid="change-password-submit">{busy ? "Saving…" : "Update password"}</Button>
        {msg.text && (
          <div className={`text-sm rounded-md px-3 py-2 ${msg.kind === "ok" ? "bg-green-50 text-green-800 border border-green-100" : "bg-red-50 text-red-700 border border-red-100"}`}>
            {msg.text}
          </div>
        )}
      </form>
    </Card>
  );
}

function HomeScreen() {
  const { user } = useAuth();
  const [today, setToday] = useState(null);
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState({ max_backdate_days: 30, requires_facial: false, requires_geo: false });
  const [showHistory, setShowHistory] = useState(false);
  const [todayHistory, setTodayHistory] = useState([]);
  const [clock, setClock] = useState(new Date());

  // Live ticking clock for the date/time card.
  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const load = async () => {
    try {
      const [t, c] = await Promise.all([
        api.get("/attendance/today"),
        api.get("/attendance/config"),
      ]);
      setToday(t.data);
      setConfig(c.data || {});
    } catch { setToday({ marked: false }); }
  };
  useEffect(() => { load(); }, []);

  const loadHistory = async () => {
    if (todayHistory.length || !today?.date) return;
    try {
      const now = new Date();
      const r = await api.get("/attendance/history", { params: { month: now.getMonth() + 1, year: now.getFullYear() } });
      setTodayHistory((r.data || []).filter((x) => x.date === today.date));
    } catch { /* noop */ }
  };

  if (!today) return <Spinner />;
  const rec = today.record || {};
  const hasIn = !!rec.check_in_at;
  const hasOut = !!rec.check_out_at;

  // Working time since check-in (live ticking until check-out captured).
  let workedLabel = null;
  if (hasIn) {
    const start = new Date(rec.check_in_at);
    const end = hasOut ? new Date(rec.check_out_at) : clock;
    const ms = Math.max(0, end - start);
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    workedLabel = `${h}h ${String(m).padStart(2, "0")}m`;
  }

  const nextAction = !hasIn ? "check_in" : !hasOut ? "check_out" : null;

  return (
    <div className="max-w-md mx-auto pb-24" data-testid="employee-home">
      {/* Header — employee name */}
      <div className="pt-2 pb-4">
        <h1 className="font-serif text-3xl text-ink leading-tight" data-testid="employee-name">
          {user?.name || "Welcome"}
        </h1>
        <p className="text-sm text-gray-500 mt-1">{labelForRoles(user)}</p>
      </div>

      {/* Date & time card (live) */}
      <Card className="mb-4" data-testid="datetime-card">
        <div className="flex items-baseline justify-between">
          <div>
            <div className="text-xs uppercase tracking-widest text-gray-500">Today</div>
            <div className="text-xl font-semibold text-ink mt-0.5">{fmtFullDate(clock)}</div>
          </div>
          <div className="tabular text-2xl font-semibold text-ink" data-testid="live-clock">
            {fmtClock(clock)}
          </div>
        </div>
      </Card>

      {/* Status section */}
      <Card className="mb-4" data-testid="status-card">
        {!hasIn ? (
          <div className="py-3 text-center">
            <Clock className="h-8 w-8 mx-auto text-gray-300 mb-2" />
            <div className="text-sm text-gray-600">No data for today yet.</div>
            <div className="text-xs text-gray-400 mt-1">Tap the button below to mark your attendance.</div>
          </div>
        ) : (
          <div>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs uppercase tracking-widest text-gray-500">
                  {hasOut ? "Hours worked" : "Working since"}
                </div>
                <div className="text-3xl font-semibold text-ink tabular mt-1" data-testid="worked-hours">
                  {workedLabel}
                </div>
              </div>
              <Badge tone={hasOut ? "green" : "blue"}>{hasOut ? "Completed" : "Active"}</Badge>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div className="bg-gray-50 rounded-md px-3 py-2">
                <div className="text-[11px] uppercase tracking-wider text-gray-500">Check in</div>
                <div className="font-semibold text-ink tabular">{fmtTime(rec.check_in_at)}</div>
              </div>
              <div className="bg-gray-50 rounded-md px-3 py-2">
                <div className="text-[11px] uppercase tracking-wider text-gray-500">Check out</div>
                <div className="font-semibold text-ink tabular">{hasOut ? fmtTime(rec.check_out_at) : "—"}</div>
              </div>
            </div>
          </div>
        )}

        {/* Past mark-ins toggle */}
        <button
          type="button"
          onClick={() => { setShowHistory((s) => !s); if (!showHistory) loadHistory(); }}
          className="mt-4 w-full text-sm text-blue-600 inline-flex items-center justify-center gap-1 hover:underline"
          data-testid="toggle-today-history"
        >
          {showHistory ? <><ChevronUp className="h-4 w-4" /> Hide today&apos;s history</> : <><ChevronDown className="h-4 w-4" /> Show today&apos;s mark-ins / outs</>}
        </button>
        {showHistory && (
          <ul className="mt-3 divide-y divide-gray-100 text-sm">
            {todayHistory.length === 0 ? (
              <li className="py-2 text-gray-500 text-center">No earlier marks today.</li>
            ) : todayHistory.map((r) => (
              <li key={r.id} className="py-2 flex items-center justify-between">
                <span className="text-gray-700">In {fmtTime(r.check_in_at)} • Out {r.check_out_at ? fmtTime(r.check_out_at) : "—"}</span>
                <Badge tone={r.check_out_at ? "green" : "blue"}>{r.check_out_at ? "Done" : "Active"}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Past dates link */}
      <div className="mb-4 text-center text-xs text-gray-500">
        Missed a day?{" "}
        <button className="text-blue-600 underline" onClick={() => setOpen({ mode: "backdate" })} data-testid="backdate-btn">
          Mark a past date
        </button>{" "}
        (up to {config.max_backdate_days ?? 30} days back).
      </div>

      {/* Primary action button — pinned visually near bottom */}
      {nextAction && (
        <Button
          onClick={() => setOpen({ mode: nextAction })}
          className="w-full !h-14 !text-base"
          data-testid={nextAction === "check_in" ? "mark-in-btn" : "mark-out-btn"}
        >
          {nextAction === "check_in" ? (
            <><LogIn className="h-5 w-5" /> Mark In</>
          ) : (
            <><LogOutIcon className="h-5 w-5" /> Mark Out</>
          )}
        </Button>
      )}
      {!nextAction && (
        <div className="rounded-md bg-green-50 border border-green-100 text-green-800 px-4 py-3 text-sm text-center" data-testid="day-done">
          ✓ Your day is complete. See you tomorrow!
        </div>
      )}

      {open && (
        <AttendanceModal
          mode={open.mode}
          config={config}
          onClose={() => setOpen(false)}
          onMarked={() => { setOpen(false); setTodayHistory([]); load(); }}
        />
      )}
    </div>
  );
}

function fmtFullDate(d) {
  try { return d.toLocaleDateString("en-IN", { weekday: "long", day: "2-digit", month: "long" }); }
  catch { return d.toDateString(); }
}
function fmtClock(d) {
  try { return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }); }
  catch { return d.toTimeString().slice(0, 8); }
}
function labelForRoles(u) {
  const roles = u?.elevated_roles || [];
  if (roles.length === 0) return "Employee";
  return `Employee • ${roles.join(" • ")}`;
}

function AttendanceModal({ mode, config = {}, onClose, onMarked }) {
  const requiresFacial = !!config.requires_facial;
  const requiresGeo = !!config.requires_geo;
  const maxBack = config.max_backdate_days ?? 30;

  const [coords, setCoords] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [snap, setSnap] = useState(null);
  // If config doesn't require facial, skip the camera entirely.
  const [skipFacial, setSkipFacial] = useState(!requiresFacial);
  const [pickedDate, setPickedDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [overwrite, setOverwrite] = useState(false);
  const [actualMode, setActualMode] = useState(mode === "backdate" ? "check_in" : mode);

  const today = new Date();
  const minDate = new Date(today.getTime() - maxBack * 24 * 3600 * 1000).toISOString().slice(0, 10);
  const maxDate = today.toISOString().slice(0, 10);

  useEffect(() => {
    // Honor the employer's config — don't even ask for geo permission
    // if this employee's attendance mode doesn't require it.
    if (!requiresGeo) {
      setCoords({ skipped: true, not_required: true });
      return;
    }
    if (!navigator.geolocation) {
      setCoords({ skipped: true });
      return;
    }
    let cancelled = false;
    navigator.geolocation.getCurrentPosition(
      (p) => { if (!cancelled) setCoords({ latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy: p.coords.accuracy }); },
      () => { if (!cancelled) setCoords({ skipped: true }); },
      { enableHighAccuracy: true, timeout: 8000 },
    );
    const t = setTimeout(() => { if (!cancelled) setCoords((c) => c || { skipped: true }); }, 8500);
    return () => { cancelled = true; clearTimeout(t); };
  }, [requiresGeo]);

  const submit = async () => {
    setBusy(true); setErr("");
    const payload = {
      method: requiresFacial && !skipFacial ? "facial" : "normal",
      type: actualMode,
      date: mode === "backdate" ? pickedDate : undefined,
      latitude: coords?.latitude ?? null,
      longitude: coords?.longitude ?? null,
      accuracy: coords?.accuracy ?? null,
      facial_image: requiresFacial && !skipFacial ? snap : null,
      overwrite,
    };
    try {
      await api.post("/attendance/mark", payload);
      onMarked();
    } catch (e) {
      if (!navigator.onLine || e?.code === "ERR_NETWORK") {
        try {
          await enqueue(payload);
          alert("You're offline — attendance is queued and will sync when you're back online.");
          onMarked();
          return;
        } catch (qe) {
          setErr("Could not queue offline. Try again.");
        }
      } else {
        setErr(fmtErr(e));
      }
    } finally { setBusy(false); }
  };

  // verified = ready to submit. If facial isn't required, no camera step needed.
  const verified = !requiresFacial || !!snap || skipFacial;
  const titleMap = { check_in: "Check in", check_out: "Check out", backdate: "Mark past date" };

  return (
    <Modal
      open={true}
      onClose={onClose}
      title={titleMap[mode]}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={busy || !verified} data-testid="confirm-attendance">
            {busy ? "Marking…" : `Mark ${actualMode === "check_in" ? "Check-in" : "Check-out"}`}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {mode === "backdate" && (
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Date"
              type="date"
              min={minDate}
              max={maxDate}
              value={pickedDate}
              onChange={(e) => setPickedDate(e.target.value)}
              data-testid="backdate-date"
            />
            <Select label="Type" value={actualMode} onChange={(e) => setActualMode(e.target.value)}>
              <option value="check_in">Check in</option>
              <option value="check_out">Check out</option>
            </Select>
            <label className="col-span-2 inline-flex items-center gap-2 text-sm">
              <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} data-testid="overwrite-toggle" />
              Replace existing record for this date (only if payroll for that month is not yet approved)
            </label>
          </div>
        )}

        {/* Facial liveness — ONLY shown when employer enabled it for this employee */}
        {requiresFacial && (
          !skipFacial ? (
            <>
              <FaceLiveness
                active={!snap}
                onPass={({ dataUrl }) => setSnap(dataUrl)}
                onError={() => setSkipFacial(true)}
              />
              {snap && (
                <div className="flex items-center justify-between bg-green-50 border border-green-100 text-green-800 rounded-md px-3 py-2 text-sm">
                  <span>Liveness verified — ready to mark.</span>
                  <button type="button" className="underline" onClick={() => setSnap(null)} data-testid="redo-liveness">Redo</button>
                </div>
              )}
            </>
          ) : (
            <div className="aspect-square w-full max-w-xs mx-auto bg-gray-100 rounded-xl border border-gray-200 flex flex-col items-center justify-center text-gray-500">
              <Camera className="h-10 w-10 mb-2" />
              <div className="text-sm">Camera unavailable — tap-only mode</div>
              <button className="mt-2 text-xs underline text-blue-600" onClick={() => setSkipFacial(false)}>Try camera again</button>
            </div>
          )
        )}

        {/* Location row — only when employer enabled geo capture */}
        {requiresGeo && (
          <div className="flex items-center gap-2 text-sm">
            <MapPin className="h-4 w-4 text-gray-500" />
            {coords?.latitude ? (
              <span className="text-gray-700 tabular" data-testid="loc-status">
                Location captured{" "}
                <span className="text-gray-400">(±{Math.round(coords.accuracy)}m)</span>
              </span>
            ) : coords?.skipped ? (
              <span className="text-gray-500" data-testid="loc-status">
                Location not captured — that&apos;s OK, you can still mark.
              </span>
            ) : (
              <span className="text-gray-500" data-testid="loc-status">
                Acquiring location… (optional)
              </span>
            )}
          </div>
        )}

        {err && <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">{err}</div>}
      </div>
    </Modal>
  );
}

function HistoryScreen() {
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());
  const [items, setItems] = useState([]);
  const load = async () => { setItems(null); try { setItems((await api.get("/attendance/history", { params: { month, year } })).data); } catch { setItems([]); } };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [month, year]);

  return (
    <div>
      <PageHeader title="My attendance" subtitle="Your monthly attendance history." />
      <div className="grid grid-cols-2 gap-3 mb-4 max-w-md">
        <Select label="Month" value={month} onChange={(e) => setMonth(Number(e.target.value))}>
          {[1,2,3,4,5,6,7,8,9,10,11,12].map((m) => <option key={m} value={m}>{monthName(m)}</option>)}
        </Select>
        <Input label="Year" type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} />
      </div>
      {items === null ? <Spinner /> : items.length === 0 ? (
        <Empty icon={Clock} title="No records this month" />
      ) : (
        <Card className="!p-0 overflow-hidden">
          <ul className="divide-y divide-gray-100">
            {items.map((r) => (
              <li key={r.id} className="px-4 py-3 flex items-center justify-between text-sm">
                <div>
                  <div className="font-medium text-ink">{fmtDate(r.date)}</div>
                  <div className="text-xs text-gray-500">In {fmtTime(r.check_in_at)} • Out {r.check_out_at ? fmtTime(r.check_out_at) : "—"}</div>
                </div>
                <Badge tone={r.check_out_at ? "green" : "blue"}>{r.check_out_at ? "Completed" : "In progress"}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function LeavesScreen() {
  const [tab, setTab] = useState("apply");
  const [balances, setBalances] = useState([]);
  const [apps, setApps] = useState([]);
  const [form, setForm] = useState({ leave_type: "", from_date: "", to_date: "", half_day: false, reason: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const [b, a] = await Promise.all([api.get("/leave/balances"), api.get("/leave/applications")]);
    setBalances(b.data); setApps(a.data);
    if (b.data.length && !form.leave_type) setForm((f) => ({ ...f, leave_type: b.data[0].leave_type }));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const apply = async (e) => {
    e?.preventDefault?.(); setBusy(true); setErr("");
    try { await api.post("/leave/apply", form); setForm({ ...form, from_date: "", to_date: "", half_day: false, reason: "" }); setTab("history"); load(); }
    catch (e2) { setErr(fmtErr(e2)); } finally { setBusy(false); }
  };

  return (
    <div>
      <PageHeader title="Leaves" subtitle="Apply for leave and view your history." />
      <div className="inline-flex bg-gray-100 rounded-md p-1 mb-4">
        <button onClick={() => setTab("apply")} className={`h-9 px-3 rounded-md text-sm font-medium ${tab === "apply" ? "bg-white shadow-sm text-ink" : "text-gray-600"}`} data-testid="tab-apply">Apply</button>
        <button onClick={() => setTab("history")} className={`h-9 px-3 rounded-md text-sm font-medium ${tab === "history" ? "bg-white shadow-sm text-ink" : "text-gray-600"}`} data-testid="tab-history">History</button>
      </div>

      {tab === "apply" ? (
        <Card>
          <form onSubmit={apply} className="space-y-3">
            <div className="grid sm:grid-cols-2 gap-3">
              <Select label="Leave type" value={form.leave_type} onChange={(e) => setForm({ ...form, leave_type: e.target.value })} required data-testid="leave-type">
                <option value="" disabled>Select…</option>
                {balances.map((b) => <option key={b.id} value={b.leave_type}>{b.leave_type} (avail {(b.quota - (b.used || 0) - (b.pending || 0)).toFixed(1)})</option>)}
              </Select>
              <label className="inline-flex items-center gap-2 mt-7">
                <input type="checkbox" checked={form.half_day} onChange={(e) => setForm({ ...form, half_day: e.target.checked })} data-testid="half-day" />
                <span className="text-sm">Half day</span>
              </label>
            </div>
            <div className="grid sm:grid-cols-2 gap-3">
              <Input label="From" type="date" required value={form.from_date} onChange={(e) => setForm({ ...form, from_date: e.target.value, to_date: form.to_date || e.target.value })} data-testid="leave-from" />
              <Input label="To" type="date" required value={form.to_date} onChange={(e) => setForm({ ...form, to_date: e.target.value })} data-testid="leave-to" />
            </div>
            <Input label="Reason" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="Optional" />
            {err && <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">{err}</div>}
            <div className="flex justify-end pt-1">
              <Button type="submit" disabled={busy} data-testid="apply-leave-btn">{busy ? "Submitting…" : "Submit application"}</Button>
            </div>
          </form>
        </Card>
      ) : apps.length === 0 ? (
        <Empty icon={Calendar} title="No applications yet" />
      ) : (
        <Card className="!p-0 overflow-hidden">
          <ul className="divide-y divide-gray-100">
            {apps.map((a) => (
              <li key={a.id} className="px-4 py-3 flex items-center justify-between text-sm">
                <div>
                  <div className="font-medium text-ink">{a.leave_type} • {a.days} day(s)</div>
                  <div className="text-xs text-gray-500">{fmtDate(a.from_date)} → {fmtDate(a.to_date)} • {a.reason || "—"}</div>
                </div>
                <Badge tone={a.status === "approved" ? "green" : a.status === "rejected" ? "red" : "yellow"}>{a.status}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function SlipsScreen() {
  const [items, setItems] = useState(null);
  useEffect(() => { api.get("/payroll/my").then((r) => setItems(r.data)).catch(() => setItems([])); }, []);

  const dl = async (it) => {
    const res = await api.get(`/payroll/items/${it.id}/slip`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a"); a.href = url; a.download = `slip-${it.month}-${it.year}.pdf`; a.click(); URL.revokeObjectURL(url);
  };

  return (
    <div>
      <PageHeader title="Salary slips" subtitle="Download approved monthly salary slips." />
      {items === null ? <Spinner /> : items.length === 0 ? (
        <Empty icon={ScrollText} title="No salary slips yet" hint="Slips appear here once your employer approves the monthly payroll run." />
      ) : (
        <Card className="!p-0 overflow-hidden">
          <ul className="divide-y divide-gray-100">
            {items.map((it) => (
              <li key={it.id} className="px-4 py-3 flex items-center justify-between text-sm" data-testid={`slip-row-${it.id}`}>
                <div>
                  <div className="font-medium text-ink">{monthName(it.month)} {it.year}</div>
                  <div className="text-xs text-gray-500 tabular">Net ₹{fmtINR(it.net_salary)} • {it.payable_days} days</div>
                </div>
                <Button variant="secondary" onClick={() => dl(it)} data-testid={`dl-slip-${it.id}`}><Download className="h-4 w-4" />PDF</Button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}


/* =====================================================================
   ACCOUNTANT WORKFLOW
   Visible only when user.elevated_roles includes "accountant".
   Reuses the same /api/payroll/* endpoints the employer uses (backend
   gates with _can_run_payroll which already allows accountants).
===================================================================== */

function AccountantPayroll() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState(null);
  const [open, setOpen] = useState(false);
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = async () => {
    setRuns(null);
    try { setRuns((await api.get("/payroll/runs")).data); } catch { setRuns([]); }
  };
  useEffect(() => { load(); }, []);

  const generate = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/payroll/generate", { month: Number(month), year: Number(year) });
      setOpen(false); load();
      navigate(`/me/payroll/${data.id}`);
    } catch (e2) { setErr(fmtErr(e2)); } finally { setBusy(false); }
  };

  return (
    <div data-testid="accountant-payroll">
      <PageHeader
        title="Payroll"
        subtitle="Generate monthly runs, edit deductions and submit for approval."
        action={<Button onClick={() => setOpen(true)} data-testid="generate-run"><Plus className="h-4 w-4" />Generate run</Button>}
      />
      {runs === null ? <Spinner /> : runs.length === 0 ? (
        <Empty icon={ScrollText} title="No payroll runs yet" hint="Generate a draft run for the current month." action={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Generate run</Button>} />
      ) : (
        <div className="space-y-3">
          {runs.map((r) => (
            <Card key={r.id} data-testid={`run-card-${r.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold text-ink">{monthName(r.month)} {r.year}</div>
                  <div className="text-xs text-gray-500">{r.items_count} employees • {r.working_days}-day basis</div>
                  <div className="text-[11px] text-gray-400 mt-1">Generated: {fmtDate(r.generated_at)}</div>
                </div>
                <Badge tone={statusTone(r.status)}>{r.status.replace("_", " ")}</Badge>
              </div>
              <div className="mt-3 flex justify-end">
                <Button variant="secondary" onClick={() => navigate(`/me/payroll/${r.id}`)} data-testid={`open-run-${r.id}`}>Open →</Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Generate payroll"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={generate} disabled={busy} data-testid="confirm-generate">{busy ? "Generating…" : "Generate"}</Button>
          </>
        }
      >
        <div className="grid grid-cols-2 gap-3">
          <Select label="Month" value={month} onChange={(e) => setMonth(e.target.value)}>
            {[1,2,3,4,5,6,7,8,9,10,11,12].map((m) => <option key={m} value={m}>{monthName(m)}</option>)}
          </Select>
          <Input label="Year" type="number" value={year} onChange={(e) => setYear(e.target.value)} />
        </div>
        <p className="text-sm text-gray-500 mt-3">A draft run will calculate present days, paid leaves and net payable for every active employee. You can re-generate while the run is still draft.</p>
        {err && <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2 mt-3">{err}</div>}
      </Modal>
    </div>
  );
}

function AccountantPayrollRun() {
  const navigate = useNavigate();
  const runId = window.location.pathname.split("/").pop();
  const [run, setRun] = useState(null);
  const [items, setItems] = useState([]);
  const { confirm, ConfirmHost } = useConfirm();

  const load = async () => {
    const { data } = await api.get(`/payroll/runs/${runId}`);
    setRun(data.run); setItems(data.items);
  };
  useEffect(() => { load(); }, [runId]);

  const submit = async () => {
    const ok = await confirm({
      kind: "simple",
      title: "Submit for approval?",
      body: "After submission, your employer can approve or reject the run. Deductions can no longer be edited.",
    });
    if (!ok) return;
    try { await api.post(`/payroll/runs/${runId}/submit`, {}); load(); }
    catch (e) { alert(fmtErr(e)); }
  };

  const editDeduction = async (item) => {
    const v = window.prompt(`Deduction for ${item.employee_name} (₹).`, item.deductions || 0);
    if (v === null) return;
    const d = Number(v);
    if (Number.isNaN(d) || d < 0) return;
    try { await api.put(`/payroll/items/${item.id}/deductions`, { deductions: d }); load(); }
    catch (e) { alert(fmtErr(e)); }
  };

  const downloadSlip = async (item) => {
    const res = await api.get(`/payroll/items/${item.id}/slip`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a"); a.href = url; a.download = `slip-${item.emp_code}-${run.year}-${String(run.month).padStart(2,"0")}.pdf`; a.click(); URL.revokeObjectURL(url);
  };

  const disburse = async (item, method) => {
    try { await api.post(`/payroll/items/${item.id}/disburse`, { method }); load(); }
    catch (e) { alert(fmtErr(e)); }
  };

  if (!run) return <Spinner />;
  const totalGross = items.reduce((s, i) => s + (i.gross_salary || 0), 0);
  const totalDeduct = items.reduce((s, i) => s + (i.deductions || 0), 0);
  const total = items.reduce((s, i) => s + (i.net_salary || 0), 0);
  const canEdit = run.status === "draft";
  const canDisburse = run.status === "approved" || run.status === "disbursed";

  return (
    <div className="pb-20" data-testid="accountant-payroll-run">
      {ConfirmHost}
      <PageHeader
        title={`${monthName(run.month)} ${run.year}`}
        subtitle={`${items.length} employees • Total ₹${fmtINR(total)}`}
        action={
          <div className="flex flex-wrap gap-2 items-center">
            <Badge tone={statusTone(run.status)}>{run.status.replace("_", " ")}</Badge>
            {canEdit && (
              <Button variant="secondary" onClick={submit} data-testid="submit-run">
                <Send className="h-4 w-4" />Submit for approval
              </Button>
            )}
          </div>
        }
      />

      {/* Totals card — gross / deductions / net for whole run */}
      <Card className="mb-4 !p-4" data-testid="payroll-totals">
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-gray-500">Total gross</div>
            <div className="text-lg font-semibold text-ink tabular mt-0.5" data-testid="total-gross">₹{fmtINR(totalGross)}</div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-gray-500">Deductions</div>
            <div className="text-lg font-semibold text-red-700 tabular mt-0.5" data-testid="total-deductions">₹{fmtINR(totalDeduct)}</div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-gray-500">Net payable</div>
            <div className="text-lg font-semibold text-green-700 tabular mt-0.5" data-testid="total-net">₹{fmtINR(total)}</div>
          </div>
        </div>
      </Card>

      {/* Mobile-friendly list of items */}
      <div className="space-y-3">
        {items.map((i) => (
          <Card key={i.id} className="!p-4" data-testid={`item-row-${i.id}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-medium text-ink truncate">{i.employee_name}</div>
                <div className="text-xs text-gray-500 font-mono">{i.emp_code}</div>
              </div>
              <div className="text-right">
                <div className="text-xs text-gray-500">Net</div>
                <div className="font-semibold text-ink tabular">₹{fmtINR(i.net_salary)}</div>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <div className="bg-gray-50 rounded-md px-2 py-1.5">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">Present</div>
                <div className="font-semibold tabular">{i.present_days}</div>
              </div>
              <div className="bg-gray-50 rounded-md px-2 py-1.5">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">Leaves</div>
                <div className="font-semibold tabular">{i.paid_leave_days}</div>
              </div>
              <div className="bg-gray-50 rounded-md px-2 py-1.5">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">Gross</div>
                <div className="font-semibold tabular">₹{fmtINR(i.gross_salary)}</div>
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between text-sm">
              <span className="text-gray-600">
                Deductions:{" "}
                {canEdit ? (
                  <button className="text-blue-600 underline" onClick={() => editDeduction(i)} data-testid={`edit-deduct-${i.id}`}>
                    ₹{fmtINR(i.deductions || 0)}
                  </button>
                ) : (
                  <span className="tabular">₹{fmtINR(i.deductions || 0)}</span>
                )}
              </span>
              {(run.status === "approved" || run.status === "disbursed") && (
                <button onClick={() => downloadSlip(i)} className="text-blue-600 inline-flex items-center gap-1 text-xs" data-testid={`slip-${i.id}`}>
                  <Download className="h-3.5 w-3.5" />Slip
                </button>
              )}
            </div>
            {canDisburse && !i.disbursement && (
              <div className="mt-2 flex gap-2">
                <button onClick={() => disburse(i, "cash")} className="flex-1 h-9 rounded-md text-xs font-medium bg-gray-50 hover:bg-gray-100" data-testid={`pay-cash-${i.id}`}>
                  <Banknote className="h-3.5 w-3.5 inline-block -mt-px mr-1" />Cash
                </button>
                <button onClick={() => disburse(i, "online")} className="flex-1 h-9 rounded-md text-xs font-medium bg-blue-50 text-blue-700 hover:bg-blue-100" data-testid={`pay-online-${i.id}`}>
                  Online
                </button>
              </div>
            )}
            {i.disbursement && (
              <div className="mt-2">
                <Badge tone="green">{i.disbursement.method.toUpperCase()} • {i.disbursement.txn_id}</Badge>
              </div>
            )}
          </Card>
        ))}
      </div>

      <div className="mt-4 text-xs text-gray-500">
        * Online disbursement is currently <b>MOCKED</b>.
      </div>
      <div className="mt-4">
        <Button variant="ghost" onClick={() => navigate("/me/payroll")}>← Back to runs</Button>
      </div>
    </div>
  );
}

function statusTone(s) {
  if (s === "draft") return "yellow";
  if (s === "pending_approval") return "blue";
  if (s === "approved") return "blue";
  if (s === "disbursed") return "green";
  if (s === "rejected") return "red";
  return "neutral";
}
