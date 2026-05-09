import React, { useEffect, useRef, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Shell from "../components/Shell";
import { Button, Card, Input, Select, PageHeader, Empty, Modal, Badge, StatTile, Spinner } from "../components/ui/Primitives";
import { api, fmtErr, fmtDate, fmtINR, fmtTime, monthName } from "../lib/api";
import { Camera, MapPin, LogIn, LogOut as LogOutIcon, Calendar, Clock, ScrollText, Download, Plus, Home, History } from "lucide-react";

const NAV = [
  { id: "home", to: "/me", end: true, label: "Home", icon: Home },
  { id: "history", to: "/me/history", label: "History", icon: History },
  { id: "leaves", to: "/me/leaves", label: "Leaves", icon: Calendar },
  { id: "slips", to: "/me/slips", label: "Salary", icon: ScrollText },
];

export default function EmployeeApp() {
  return (
    <Shell nav={NAV}>
      <Routes>
        <Route index element={<HomeScreen />} />
        <Route path="history" element={<HistoryScreen />} />
        <Route path="leaves" element={<LeavesScreen />} />
        <Route path="slips" element={<SlipsScreen />} />
        <Route path="*" element={<Navigate to="/me" replace />} />
      </Routes>
    </Shell>
  );
}

function HomeScreen() {
  const [today, setToday] = useState(null);
  const [balances, setBalances] = useState([]);
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [t, b] = await Promise.all([api.get("/attendance/today"), api.get("/leave/balances")]);
      setToday(t.data); setBalances(b.data);
    } catch { setToday({ marked: false }); }
  };
  useEffect(() => { load(); }, []);

  if (!today) return <Spinner />;
  const rec = today.record || {};
  const hasIn = !!rec.check_in_at;
  const hasOut = !!rec.check_out_at;

  return (
    <div>
      <PageHeader title="Today" subtitle={fmtDate(today.date)} />

      <Card className="mb-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-widest text-gray-500">Status</div>
            <div className="text-2xl font-semibold text-ink mt-0.5">
              {!hasIn ? "Not marked yet" : hasOut ? "Day completed" : "Checked in"}
            </div>
            <div className="text-sm text-gray-600 mt-1">
              {hasIn && <span>In: <b className="tabular">{fmtTime(rec.check_in_at)}</b></span>}
              {hasOut && <span className="ml-3">Out: <b className="tabular">{fmtTime(rec.check_out_at)}</b></span>}
            </div>
          </div>
          <Badge tone={hasOut ? "green" : hasIn ? "blue" : "neutral"}>
            {hasOut ? "Done" : hasIn ? "Active" : "Pending"}
          </Badge>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-2">
          <Button onClick={() => setOpen("check_in")} disabled={hasIn} data-testid="check-in-btn">
            <LogIn className="h-4 w-4" />Check in
          </Button>
          <Button variant="secondary" onClick={() => setOpen("check_out")} disabled={!hasIn || hasOut} data-testid="check-out-btn">
            <LogOutIcon className="h-4 w-4" />Check out
          </Button>
        </div>
      </Card>

      <h3 className="text-sm uppercase tracking-widest text-gray-500 mb-2">Leave balances</h3>
      {balances.length === 0 ? (
        <Card className="text-sm text-gray-500">No leave types configured yet.</Card>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {balances.map((b) => (
            <Card key={b.id} className="!p-4">
              <div className="text-xs uppercase tracking-widest text-gray-500">{b.leave_type}</div>
              <div className="text-2xl font-semibold text-ink tabular mt-1">{(b.quota - (b.used || 0) - (b.pending || 0)).toFixed(1)}</div>
              <div className="text-xs text-gray-500 mt-0.5">of {b.quota} • {b.used || 0} used</div>
            </Card>
          ))}
        </div>
      )}

      {open && (
        <AttendanceModal
          mode={open}
          onClose={() => setOpen(false)}
          onMarked={() => { setOpen(false); load(); }}
        />
      )}
    </div>
  );
}

function AttendanceModal({ mode, onClose, onMarked }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [stream, setStream] = useState(null);
  const [coords, setCoords] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [snap, setSnap] = useState(null);
  const [useFacial, setUseFacial] = useState(true);

  useEffect(() => {
    let s;
    (async () => {
      if (useFacial) {
        try {
          s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
          setStream(s);
          if (videoRef.current) videoRef.current.srcObject = s;
        } catch (e) {
          setUseFacial(false); // fallback to tap
        }
      }
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          (p) => setCoords({ latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy: p.coords.accuracy }),
          (e) => setCoords({ error: e.message }),
          { enableHighAccuracy: true, timeout: 10000 }
        );
      }
    })();
    return () => { if (s) s.getTracks().forEach((t) => t.stop()); };
    // eslint-disable-next-line
  }, [useFacial]);

  const capture = () => {
    if (!videoRef.current || !canvasRef.current) return null;
    const v = videoRef.current; const c = canvasRef.current;
    c.width = 320; c.height = 320;
    const ctx = c.getContext("2d");
    const ratio = Math.max(c.width / v.videoWidth, c.height / v.videoHeight);
    const sw = c.width / ratio; const sh = c.height / ratio;
    const sx = (v.videoWidth - sw) / 2; const sy = (v.videoHeight - sh) / 2;
    ctx.drawImage(v, sx, sy, sw, sh, 0, 0, c.width, c.height);
    const dataUrl = c.toDataURL("image/jpeg", 0.7);
    setSnap(dataUrl);
    return dataUrl;
  };

  const submit = async () => {
    setBusy(true); setErr("");
    try {
      let img = snap;
      if (useFacial && !img) img = capture();
      await api.post("/attendance/mark", {
        method: useFacial ? "facial" : "normal",
        type: mode,
        latitude: coords?.latitude,
        longitude: coords?.longitude,
        accuracy: coords?.accuracy,
        facial_image: img,
      });
      onMarked();
    } catch (e) { setErr(fmtErr(e)); } finally { setBusy(false); }
  };

  return (
    <Modal open={true} onClose={onClose} title={mode === "check_in" ? "Check in" : "Check out"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={busy} data-testid="confirm-attendance">{busy ? "Marking…" : (mode === "check_in" ? "Mark Check-in" : "Mark Check-out")}</Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="aspect-square w-full max-w-xs mx-auto bg-gray-100 rounded-xl overflow-hidden border border-gray-200 relative">
          {useFacial ? (
            <>
              {snap ? (
                <img src={snap} alt="captured" className="w-full h-full object-cover" />
              ) : (
                <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
              )}
              <button type="button" onClick={() => snap ? setSnap(null) : capture()} className="absolute bottom-2 right-2 h-10 w-10 rounded-full bg-white/90 border border-gray-200 inline-flex items-center justify-center" data-testid="capture-btn" title={snap ? "Retake" : "Capture"}>
                <Camera className="h-4 w-4" />
              </button>
            </>
          ) : (
            <div className="h-full w-full flex flex-col items-center justify-center text-gray-500">
              <Camera className="h-10 w-10 mb-2" />
              <div className="text-sm">Camera unavailable — tap-only mode</div>
            </div>
          )}
          <canvas ref={canvasRef} className="hidden" />
        </div>

        <div className="flex items-center gap-2 text-sm">
          <MapPin className="h-4 w-4 text-gray-500" />
          {coords?.error ? (
            <span className="text-amber-600">Location error: {coords.error}</span>
          ) : coords ? (
            <span className="text-gray-700">{coords.latitude.toFixed(5)}, {coords.longitude.toFixed(5)} <span className="text-gray-400">(±{Math.round(coords.accuracy)}m)</span></span>
          ) : (
            <span className="text-gray-500">Acquiring location…</span>
          )}
        </div>

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
