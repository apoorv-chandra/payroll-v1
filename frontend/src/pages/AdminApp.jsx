import React, { useEffect, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Shell from "../components/Shell";
import { Button, Card, Input, PageHeader, Empty, Modal, Badge, StatTile, Spinner } from "../components/ui/Primitives";
import { api, fmtErr, fmtDate } from "../lib/api";
import useConfirm from "../lib/useConfirm";
import { LayoutDashboard, Building2, ClipboardList, Trash2, Plus, Users, Briefcase, ScrollText, Settings as SettingsIcon } from "lucide-react";

const NAV = [
  { id: "dashboard", to: "/admin", end: true, label: "Overview", icon: LayoutDashboard },
  { id: "employers", to: "/admin/employers", label: "Employers", icon: Building2 },
  { id: "platform", to: "/admin/platform", label: "Platform", icon: SettingsIcon },
  { id: "audit", to: "/admin/audit", label: "Audit", icon: ClipboardList },
];

export default function AdminApp() {
  return (
    <Shell nav={NAV}>
      <Routes>
        <Route index element={<Overview />} />
        <Route path="employers" element={<Employers />} />
        <Route path="platform" element={<PlatformSettings />} />
        <Route path="audit" element={<Audit />} />
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Routes>
    </Shell>
  );
}

function Overview() {
  const [stats, setStats] = useState(null);
  useEffect(() => { api.get("/admin/stats").then((r) => setStats(r.data)).catch(() => setStats({})); }, []);
  return (
    <div>
      <PageHeader title="Platform overview" subtitle="Tenants, employees, attendance & active payroll runs across the platform." />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Tenants" value={stats?.tenants ?? "—"} icon={Building2} />
        <StatTile label="Employees" value={stats?.employees ?? "—"} icon={Users} />
        <StatTile label="Attended Today" value={stats?.attendance_today ?? "—"} icon={Briefcase} />
        <StatTile label="Open Payrolls" value={stats?.active_payrolls ?? "—"} icon={ScrollText} />
      </div>

      <Card className="mt-6">
        <h3 className="font-semibold text-ink mb-2">How this works</h3>
        <ol className="list-decimal pl-5 text-sm text-gray-700 space-y-1.5">
          <li>Onboard an <b>Employer (tenant)</b> from the Employers page — this creates an isolated workspace.</li>
          <li>Share the employer admin&apos;s email & password with them.</li>
          <li>The employer signs in, configures attendance + leave types, adds employees.</li>
          <li>Employees mark attendance from a phone (PWA), apply leaves, and download salary slips.</li>
        </ol>
      </Card>
    </div>
  );
}

function Employers() {
  const [list, setList] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", admin_email: "", admin_password: "", admin_name: "", phone: "", address: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const [createdCode, setCreatedCode] = useState(null);

  const load = async () => {
    setList(null);
    try { const { data } = await api.get("/admin/employers"); setList(data); } catch { setList([]); }
  };
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/admin/employers", form);
      setOpen(false);
      setCreatedCode({ code: data.signup_code, name: form.name });
      setForm({ name: "", admin_email: "", admin_password: "", admin_name: "", phone: "", address: "" });
      load();
    } catch (e2) { setErr(fmtErr(e2)); } finally { setBusy(false); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this employer and ALL their data? This cannot be undone.")) return;
    await api.delete(`/admin/employers/${id}`);
    load();
  };

  return (
    <div>
      <PageHeader
        title="Employers (Tenants)"
        subtitle="Independent workspaces. Data is fully isolated between tenants."
        action={<Button onClick={() => setOpen(true)} data-testid="add-employer-button"><Plus className="h-4 w-4" />Add employer</Button>}
      />
      {list === null ? (
        <div className="flex items-center gap-2 text-gray-500"><Spinner /> Loading…</div>
      ) : list.length === 0 ? (
        <Empty icon={Building2} title="No employers yet" hint="Onboard your first employer to get started." action={<Button onClick={() => setOpen(true)} data-testid="add-employer-button-empty"><Plus className="h-4 w-4" />Add employer</Button>} />
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {list.map((t) => (
            <Card key={t.id} data-testid={`employer-card-${t.id}`}>
              <div className="flex items-start justify-between">
                <div className="min-w-0">
                  <div className="font-semibold text-ink truncate">{t.name}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{t.admin?.email}</div>
                </div>
                <Badge tone={t.active ? "green" : "neutral"}>{t.active ? "Active" : "Inactive"}</Badge>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
                <div><div className="text-xs text-gray-500">Employees</div><div className="font-medium tabular">{t.employee_count}</div></div>
                <div><div className="text-xs text-gray-500">Onboarded</div><div className="font-medium">{fmtDate(t.created_at)}</div></div>
              </div>
              {t.signup_code && (
                <div className="mt-3 px-3 py-2 bg-gray-50 border border-dashed border-gray-300 rounded-md">
                  <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">Invite code (immutable)</div>
                  <div className="font-mono text-lg tracking-[0.2em] text-ink select-all" data-testid={`invite-code-${t.id}`}>{t.signup_code}</div>
                </div>
              )}
              <div className="mt-4 flex gap-2 justify-end">
                <Button variant="danger" onClick={() => del(t.id)} data-testid={`delete-employer-${t.id}`}><Trash2 className="h-4 w-4" />Delete</Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Onboard an employer"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={create} disabled={busy} data-testid="submit-employer">{busy ? "Creating…" : "Create"}</Button>
          </>
        }
      >
        <form onSubmit={create} className="space-y-3">
          <Input label="Company name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="employer-name" />
          <div className="grid sm:grid-cols-2 gap-3">
            <Input label="Admin name" required value={form.admin_name} onChange={(e) => setForm({ ...form, admin_name: e.target.value })} data-testid="employer-admin-name" />
            <Input label="Admin email" type="email" required value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })} data-testid="employer-admin-email" />
          </div>
          <Input label="Admin password" type="text" required value={form.admin_password} onChange={(e) => setForm({ ...form, admin_password: e.target.value })} hint="Share this with the employer; they can change it later." data-testid="employer-admin-password" />
          <div className="grid sm:grid-cols-2 gap-3">
            <Input label="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <Input label="Address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          </div>
          {err && <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">{err}</div>}
        </form>
      </Modal>

      {/* Post-creation: show the auto-allotted invite code prominently. */}
      <Modal
        open={!!createdCode}
        onClose={() => setCreatedCode(null)}
        title="Employer onboarded"
        footer={<Button onClick={() => setCreatedCode(null)} data-testid="close-created-code">Done</Button>}
      >
        {createdCode && (
          <div className="text-center" data-testid="created-employer-code">
            <p className="text-sm text-gray-600 mb-3">
              <strong>{createdCode.name}</strong> can now invite employees with this code.
              It cannot be changed — share it with them privately.
            </p>
            <div className="bg-gray-50 border border-dashed border-gray-300 rounded-md px-4 py-5 font-mono text-3xl tracking-[0.35em] text-ink select-all">
              {createdCode.code}
            </div>
            <p className="text-xs text-gray-400 mt-3">Treat this like a password.</p>
          </div>
        )}
      </Modal>
    </div>
  );
}

function PlatformSettings() {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = async () => {
    try { setS((await api.get("/admin/platform-settings")).data); } catch { setS({}); }
  };
  useEffect(() => { load(); }, []);

  const update = async (patch) => {
    setBusy(true); setSaved(false);
    try {
      await api.put("/admin/platform-settings", patch);
      await load();
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } finally { setBusy(false); }
  };

  if (!s) return <Spinner />;
  return (
    <div>
      <PageHeader title="Platform settings" subtitle="Global feature flags. Affect every tenant on this installation." />
      <div className="space-y-4">
        <Card>
          <h3 className="font-semibold text-ink mb-3">Notifications</h3>
          <label className="flex items-start gap-3 cursor-pointer">
            <input type="checkbox" checked={!!s.whatsapp_enabled} onChange={(e) => update({ whatsapp_enabled: e.target.checked })} data-testid="whatsapp-toggle" className="mt-1" />
            <span>
              <span className="font-medium text-ink block">Enable WhatsApp notifications</span>
              <span className="text-sm text-gray-500">Sends salary-ready and leave-decision alerts to employees on WhatsApp via Twilio. Requires <code>TWILIO_*</code> env vars.</span>
            </span>
          </label>
        </Card>
        <Card>
          <h3 className="font-semibold text-ink mb-3">Attendance</h3>
          <Input
            label="Maximum backdate (days)"
            type="number" min="0" max="365"
            defaultValue={s.max_backdate_days ?? 30}
            onBlur={(e) => update({ max_backdate_days: Number(e.target.value) })}
            hint="Employees can mark attendance for today and up to this many days back."
            data-testid="max-backdate"
          />
        </Card>
        {busy && <div className="text-xs text-gray-500">Saving…</div>}
        {saved && <div className="text-xs text-green-700 bg-green-50 border border-green-100 rounded-md px-3 py-2 inline-block">Saved.</div>}
      </div>
    </div>
  );
}

function Audit() {
  const [items, setItems] = useState(null);
  useEffect(() => { api.get("/admin/audit").then((r) => setItems(r.data)).catch(() => setItems([])); }, []);
  return (
    <div>
      <PageHeader title="Audit log" subtitle="Last 100 events across all tenants." />
      {items === null ? <Spinner /> : items.length === 0 ? (
        <Empty icon={ClipboardList} title="No events yet" />
      ) : (
        <Card className="!p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr className="text-left text-xs uppercase tracking-wider text-gray-500">
                  <th className="py-3 px-4">When</th>
                  <th className="py-3 px-4">Action</th>
                  <th className="py-3 px-4">Tenant</th>
                  <th className="py-3 px-4">Target</th>
                </tr>
              </thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.id} className="border-t border-gray-100">
                    <td className="py-3 px-4 text-gray-700">{fmtDate(a.created_at)}</td>
                    <td className="py-3 px-4 font-mono text-xs">{a.action}</td>
                    <td className="py-3 px-4 text-gray-600">{a.tenant_id ? a.tenant_id.slice(0, 8) : "—"}</td>
                    <td className="py-3 px-4 text-gray-600">{a.target ? String(a.target).slice(0, 12) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

