/* eslint-disable react/no-unescaped-entities */
import React, { useEffect, useMemo, useState } from "react";
import { Routes, Route, Navigate, useNavigate } from "react-router-dom";
import Shell from "../components/Shell";
import { Button, Card, Input, Select, PageHeader, Empty, Modal, Badge, StatTile, Spinner } from "../components/ui/Primitives";
import { api, fmtErr, fmtDate, fmtINR, fmtTime, monthName } from "../lib/api";
import { LayoutDashboard, Users, Calendar, ScrollText, Plus, Trash2, Pencil, Settings, MapPin, Check, X, Download, Banknote, Send, UserPlus, Copy, Link2, KeyRound, Eye, RotateCw } from "lucide-react";
import GeofenceMap from "../components/GeofenceMap";
import PinMap from "../components/PinMap";
import useConfirm from "../lib/useConfirm";

const NAV = [
  { id: "dashboard", to: "/employer", end: true, label: "Overview", icon: LayoutDashboard },
  { id: "employees", to: "/employer/employees", label: "Employees", icon: Users },
  { id: "leaves", to: "/employer/leaves", label: "Leaves", icon: Calendar },
  { id: "payroll", to: "/employer/payroll", label: "Payroll", icon: ScrollText },
  { id: "settings", to: "/employer/settings", label: "Settings", icon: Settings },
];

export default function EmployerApp() {
  return (
    <Shell nav={NAV}>
      <Routes>
        <Route index element={<Overview />} />
        <Route path="employees" element={<Employees />} />
        <Route path="leaves" element={<Leaves />} />
        <Route path="payroll" element={<Payroll />} />
        <Route path="payroll/:runId" element={<PayrollRun />} />
        <Route path="payroll/:runId/summary" element={<PayrollSummary />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/employer" replace />} />
      </Routes>
    </Shell>
  );
}

function PayrollSummary() {
  const navigate = useNavigate();
  const runId = window.location.pathname.split("/").slice(-2, -1)[0];
  const [data, setData] = useState(null);
  const [view, setView] = useState("list"); // list | cards
  useEffect(() => {
    api.get(`/payroll/runs/${runId}/summary`).then((r) => setData(r.data)).catch(() => setData({ items: [] }));
  }, [runId]);
  if (!data) return <Spinner />;
  return (
    <div>
      <PageHeader
        title={`Salary summary — ${monthName(data.run?.month)} ${data.run?.year}`}
        subtitle={`${data.count} employees • Total ₹${fmtINR(data.total)} • ${data.run?.status?.replace("_"," ")}`}
        action={
          <div className="inline-flex bg-gray-100 rounded-md p-1">
            <button onClick={() => setView("list")} className={`h-9 px-3 rounded-md text-sm font-medium ${view === "list" ? "bg-white shadow-sm text-ink" : "text-gray-600"}`} data-testid="summary-list">List</button>
            <button onClick={() => setView("cards")} className={`h-9 px-3 rounded-md text-sm font-medium ${view === "cards" ? "bg-white shadow-sm text-ink" : "text-gray-600"}`} data-testid="summary-cards">Cards</button>
          </div>
        }
      />
      {view === "list" ? (
        <Card className="!p-0 overflow-hidden">
          <ul className="divide-y divide-gray-100">
            {data.items.map((i) => (
              <li key={i.id} className="px-4 py-3 flex items-center justify-between text-sm">
                <div>
                  <div className="font-medium text-ink">{i.employee_name}</div>
                  <div className="text-xs text-gray-500">{i.emp_code}{i.designation ? ` • ${i.designation}` : ""}</div>
                </div>
                <div className="text-right">
                  <div className="font-semibold text-ink tabular">₹{fmtINR(i.net_salary)}</div>
                  {i.disbursed && <div className="text-[11px] text-green-700">Disbursed</div>}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {data.items.map((i) => (
            <Card key={i.id} className="!p-4">
              <div className="text-xs text-gray-500 truncate">{i.emp_code}</div>
              <div className="font-medium text-ink truncate" title={i.employee_name}>{i.employee_name}</div>
              <div className="text-2xl font-semibold text-ink tabular mt-2">₹{fmtINR(i.net_salary)}</div>
              {i.disbursed && <Badge tone="green">Disbursed</Badge>}
            </Card>
          ))}
        </div>
      )}
      <Button variant="ghost" className="mt-4" onClick={() => navigate(`/employer/payroll/${runId}`)}>← Back</Button>
    </div>
  );
}

function Overview() {
  const [emps, setEmps] = useState([]);
  const [leaves, setLeaves] = useState([]);
  const [att, setAtt] = useState([]);
  const [tenant, setTenant] = useState(null);
  useEffect(() => {
    Promise.all([
      api.get("/employees"),
      api.get("/leave/applications", { params: { status_f: "pending" } }),
      api.get("/attendance/history"),
      api.get("/tenant/settings"),
    ]).then(([a, b, c, d]) => { setEmps(a.data); setLeaves(b.data); setAtt(c.data); setTenant(d.data); }).catch(() => {});
  }, []);
  const today = new Date().toISOString().slice(0, 10);
  const presentToday = att.filter((r) => r.date === today).length;
  return (
    <div>
      <PageHeader title={tenant?.name || "Overview"} subtitle="Today's attendance, pending leaves, and payroll status." />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Employees" value={emps.length} icon={Users} />
        <StatTile label="Present Today" value={presentToday} icon={Check} hint={`of ${emps.length}`} />
        <StatTile label="Pending Leaves" value={leaves.length} icon={Calendar} />
        <StatTile label="This Month" value={monthName(new Date().getMonth() + 1)} icon={ScrollText} hint="Run payroll →" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mt-6">
        <Card>
          <h3 className="font-semibold text-ink mb-3">Pending leave requests</h3>
          {leaves.length === 0 ? (
            <p className="text-sm text-gray-500">No pending requests.</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {leaves.slice(0, 5).map((l) => (
                <li key={l.id} className="py-2 flex items-center justify-between text-sm">
                  <div>
                    <div className="font-medium text-ink">{l.employee_name}</div>
                    <div className="text-xs text-gray-500">{l.leave_type} • {fmtDate(l.from_date)} → {fmtDate(l.to_date)}</div>
                  </div>
                  <Badge tone="yellow">Pending</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <h3 className="font-semibold text-ink mb-3">Today's attendance</h3>
          {att.filter((r) => r.date === today).length === 0 ? (
            <p className="text-sm text-gray-500">No one has checked in today.</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {att.filter((r) => r.date === today).slice(0, 5).map((r) => {
                const e = emps.find((x) => x.id === r.employee_id);
                return (
                  <li key={r.id} className="py-2 flex items-center justify-between text-sm">
                    <div className="font-medium text-ink">{e?.name || r.employee_id.slice(0, 8)}</div>
                    <div className="text-xs text-gray-500">In: {fmtTime(r.check_in_at)} {r.check_out_at && `• Out: ${fmtTime(r.check_out_at)}`}</div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function Employees() {
  const [list, setList] = useState(null);
  const [pending, setPending] = useState([]);
  const [resetReqs, setResetReqs] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyEmpForm());
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [credsFor, setCredsFor] = useState(null);   // employee for credentials modal
  const [locateFor, setLocateFor] = useState(null); // employee for locate modal
  const { confirm, ConfirmHost } = useConfirm();

  const load = async () => {
    setList(null);
    try { setList((await api.get("/employees")).data); } catch { setList([]); }
    try { setPending((await api.get("/employees/pending")).data); } catch { setPending([]); }
    try { setResetReqs((await api.get("/employees/password-reset/pending")).data); } catch { setResetReqs([]); }
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      if (editing) {
        const { password, email, emp_code, joining_date, ...patch } = form;
        await api.put(`/employees/${editing.id}`, patch);
      } else {
        await api.post("/employees", { ...form, monthly_salary: Number(form.monthly_salary) });
      }
      setOpen(false); setEditing(null); setForm(emptyEmpForm()); load();
    } catch (e2) { setErr(fmtErr(e2)); } finally { setBusy(false); }
  };
  const del = async (e) => {
    const ok = await confirm({
      kind: "type",
      title: `Remove ${e.name}?`,
      body: "This deletes the employee, their attendance, leaves and balances permanently.",
      typeText: e.name,
      danger: true,
      confirmText: "Permanently remove",
    });
    if (!ok) return;
    await api.delete(`/employees/${e.id}`); load();
  };
  const startEdit = (e) => {
    setEditing(e);
    setForm({ ...emptyEmpForm(), ...e });
    setOpen(true);
  };

  return (
    <div>
      {ConfirmHost}
      <PageHeader
        title="Employees"
        subtitle="Add, edit, or remove people in your workspace."
        action={<Button onClick={() => { setEditing(null); setForm(emptyEmpForm()); setOpen(true); }} data-testid="add-employee-button"><Plus className="h-4 w-4" />Add employee</Button>}
      />

      <PendingSignups items={pending} onChanged={load} />
      <PendingPasswordResets items={resetReqs} onChanged={load} />

      {list === null ? <Spinner /> : list.length === 0 ? (
        <Empty icon={Users} title="No employees yet" hint="Add your first employee — they'll get login credentials and can start marking attendance." action={<Button onClick={() => setOpen(true)} data-testid="add-employee-empty"><Plus className="h-4 w-4" />Add employee</Button>} />
      ) : (
        <Card className="!p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs uppercase tracking-wider text-gray-500">
                <tr>
                  <th className="py-3 px-4">Code</th>
                  <th className="py-3 px-4">Name</th>
                  <th className="py-3 px-4 hidden sm:table-cell">Designation</th>
                  <th className="py-3 px-4 hidden md:table-cell">Salary</th>
                  <th className="py-3 px-4 hidden md:table-cell">Roles</th>
                  <th className="py-3 px-4 text-right"></th>
                </tr>
              </thead>
              <tbody>
                {list.map((e) => (
                  <tr key={e.id} className="border-t border-gray-100" data-testid={`employee-row-${e.id}`}>
                    <td className="py-3 px-4 font-mono text-xs">{e.emp_code}</td>
                    <td className="py-3 px-4">
                      <div className="font-medium text-ink">{e.name}</div>
                      <div className="text-xs text-gray-500">{e.email}</div>
                    </td>
                    <td className="py-3 px-4 hidden sm:table-cell text-gray-700">{e.designation || "—"}</td>
                    <td className="py-3 px-4 hidden md:table-cell tabular">₹{fmtINR(e.monthly_salary)}</td>
                    <td className="py-3 px-4 hidden md:table-cell">
                      {(e.elevated_roles || []).length === 0 ? <span className="text-gray-400 text-xs">—</span> :
                        e.elevated_roles.map((r) => <Badge key={r} tone="blue">{r}</Badge>)}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button onClick={() => setCredsFor(e)} className="h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-blue-700" title="Credentials" data-testid={`creds-${e.id}`}><KeyRound className="h-4 w-4" /></button>
                      <button onClick={() => setLocateFor(e)} className="h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-emerald-700" title="Locate" data-testid={`locate-${e.id}`}><MapPin className="h-4 w-4" /></button>
                      <button onClick={() => startEdit(e)} className="h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700" data-testid={`edit-${e.id}`}><Pencil className="h-4 w-4" /></button>
                      <button onClick={() => del(e)} className="h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-red-600" data-testid={`del-${e.id}`}><Trash2 className="h-4 w-4" /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Modal
        open={open}
        onClose={() => { setOpen(false); setEditing(null); }}
        title={editing ? "Edit employee" : "Add employee"}
        footer={
          <>
            <Button variant="secondary" onClick={() => { setOpen(false); setEditing(null); }}>Cancel</Button>
            <Button onClick={submit} disabled={busy} data-testid="employee-submit">{busy ? "Saving…" : (editing ? "Save changes" : "Create")}</Button>
          </>
        }
      >
        <form onSubmit={submit} className="space-y-3">
          <div className="grid sm:grid-cols-2 gap-3">
            <Input label="Full name" required value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="emp-name" />
            <Input label="Employee code" required disabled={!!editing} value={form.emp_code || ""} onChange={(e) => setForm({ ...form, emp_code: e.target.value })} data-testid="emp-code" />
          </div>
          {!editing && (
            <div className="grid sm:grid-cols-2 gap-3">
              <Input label="Login email" type="email" required value={form.email || ""} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="emp-email" />
              <Input label="Login password" required value={form.password || ""} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="emp-password" />
            </div>
          )}
          <div className="grid sm:grid-cols-2 gap-3">
            <Input label="Designation" value={form.designation || ""} onChange={(e) => setForm({ ...form, designation: e.target.value })} />
            <Input label="Department" value={form.department || ""} onChange={(e) => setForm({ ...form, department: e.target.value })} />
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <Input label="Monthly salary (₹)" type="number" required value={form.monthly_salary || ""} onChange={(e) => setForm({ ...form, monthly_salary: e.target.value })} data-testid="emp-salary" />
            <Input label="Joining date" type="date" disabled={!!editing} value={form.joining_date || ""} onChange={(e) => setForm({ ...form, joining_date: e.target.value })} />
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <Input label="Bank A/C" value={form.bank_account || ""} onChange={(e) => setForm({ ...form, bank_account: e.target.value })} />
            <Input label="IFSC" value={form.ifsc || ""} onChange={(e) => setForm({ ...form, ifsc: e.target.value })} />
          </div>
          <Select label="Elevated roles (multi-select)" multiple value={form.elevated_roles || []} onChange={(e) => setForm({ ...form, elevated_roles: Array.from(e.target.selectedOptions).map((o) => o.value) })}>
            <option value="accountant">Accountant (generates payroll)</option>
            <option value="principal">Principal (approves leaves)</option>
            <option value="cashier">Cashier (cash disbursement)</option>
          </Select>
          {err && <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">{err}</div>}
        </form>
      </Modal>

      {credsFor && (
        <CredentialsModal
          employee={credsFor}
          onClose={() => setCredsFor(null)}
          onReset={load}
        />
      )}
      {locateFor && (
        <LocateEmployeeModal
          employee={locateFor}
          onClose={() => setLocateFor(null)}
        />
      )}
    </div>
  );
}

function CredentialsModal({ employee, onClose, onReset }) {
  const [data, setData] = useState(null);
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const { confirm, ConfirmHost } = useConfirm();

  const load = async () => {
    try { setData((await api.get(`/employees/${employee.id}/credentials`)).data); }
    catch { setData({ error: true }); }
  };
  useEffect(() => { load(); }, []);    // eslint-disable-line react-hooks/exhaustive-deps

  const reset = async () => {
    const ok = await confirm({
      kind: "simple",
      title: `Reset password for ${employee.name}?`,
      body: "A new temporary password will be generated. The employee's current password stops working immediately.",
      danger: true,
      confirmText: "Reset password",
    });
    if (!ok) return;
    setBusy(true);
    try {
      await api.post(`/employees/${employee.id}/reset-password`);
      await load();
      setReveal(true);
      onReset && onReset();
    } catch { /* noop */ }
    finally { setBusy(false); }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={`Credentials — ${employee.name}`}
      footer={<Button variant="secondary" onClick={onClose}>Close</Button>}
    >
      {ConfirmHost}
      <div className="space-y-3 text-sm" data-testid="credentials-body">
        <div>
          <div className="text-xs uppercase tracking-wider text-gray-500">Login email</div>
          <div className="font-mono">{data?.email || "—"}</div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-wider text-gray-500">Initial password</div>
          {data?.initial_password ? (
            <div className="mt-1 flex items-center gap-2">
              <code className="px-3 py-2 bg-gray-50 border border-gray-200 rounded-md font-mono tracking-[0.2em] text-base" data-testid="initial-password-value">
                {reveal ? data.initial_password : "••••••••"}
              </code>
              <button
                type="button"
                onClick={() => setReveal((v) => !v)}
                className="h-9 px-3 rounded-md border border-gray-200 hover:bg-gray-50 inline-flex items-center gap-1 text-xs"
                data-testid="toggle-reveal-password"
              >
                <Eye className="h-3.5 w-3.5" />{reveal ? "Hide" : "Reveal"}
              </button>
              <button
                type="button"
                onClick={async () => { try { await navigator.clipboard.writeText(data.initial_password); } catch { window.prompt("Copy:", data.initial_password); } }}
                className="h-9 px-3 rounded-md border border-gray-200 hover:bg-gray-50 inline-flex items-center gap-1 text-xs"
                data-testid="copy-initial-password"
              >
                <Copy className="h-3.5 w-3.5" />Copy
              </button>
            </div>
          ) : (
            <div className="text-gray-500 italic mt-1">
              Employee has already logged in. Initial password is no longer available for security.
            </div>
          )}
        </div>

        <div className="text-xs text-gray-500">
          {data?.first_login_at && <div>First login: {fmtDate(data.first_login_at)}</div>}
          {data?.password_changed_at && <div>Password changed: {fmtDate(data.password_changed_at)}</div>}
        </div>

        <hr className="border-gray-100" />

        <Button variant="secondary" onClick={reset} disabled={busy} data-testid="reset-password-btn">
          <RotateCw className="h-4 w-4" />{busy ? "Resetting…" : "Reset password"}
        </Button>
        <p className="text-xs text-gray-500">
          Resets the employee's password to a new temporary one (shown above after reset). The employee will be forced to use it on next sign-in.
        </p>
      </div>
    </Modal>
  );
}

function LocateEmployeeModal({ employee, onClose }) {
  const [items, setItems] = useState(null);
  const [pinFor, setPinFor] = useState(null);

  useEffect(() => {
    api.get(`/attendance/locations/${employee.id}`)
      .then((r) => setItems(r.data || []))
      .catch(() => setItems([]));
  }, [employee.id]);

  return (
    <Modal
      open
      onClose={onClose}
      title={`Locate — ${employee.name}`}
      footer={<Button variant="secondary" onClick={onClose}>Close</Button>}
    >
      {items === null ? <Spinner /> : items.length === 0 ? (
        <div className="text-sm text-gray-500 bg-gray-50 border border-gray-100 rounded-md px-3 py-3 text-center">
          No location records (employee may not have shared location).
        </div>
      ) : (
        <ul className="divide-y divide-gray-100 -mx-1 max-h-[50vh] overflow-y-auto" data-testid="locate-list">
          {items.map((it) => (
            <li key={it.id} className="py-2.5 px-1 flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-ink">{fmtDate(it.date)}</div>
                <div className="text-xs text-gray-500 tabular">
                  In: {fmtTime(it.check_in_at)} · Out: {it.check_out_at ? fmtTime(it.check_out_at) : "—"}
                </div>
              </div>
              <button
                onClick={() => setPinFor(it)}
                className="h-9 px-3 rounded-md text-xs font-medium bg-blue-50 text-blue-700 hover:bg-blue-100 inline-flex items-center gap-1"
                data-testid={`locate-map-${it.date}`}
              >
                <MapPin className="h-3.5 w-3.5" />Map it
              </button>
            </li>
          ))}
        </ul>
      )}

      {pinFor && (
        <Modal
          open
          onClose={() => setPinFor(null)}
          title={`${fmtDate(pinFor.date)} — ${employee.name}`}
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
    </Modal>
  );
}

function PendingPasswordResets({ items, onChanged }) {
  if (!items || items.length === 0) return null;
  const act = async (id, action) => {
    try { await api.post(`/employees/password-reset/${id}/${action}`); onChanged && onChanged(); }
    catch (e) { alert(fmtErr(e)); }
  };
  return (
    <div className="mb-5" data-testid="pending-resets-panel">
      <Card className="!p-0 overflow-hidden border-orange-200">
        <div className="px-4 py-3 bg-orange-50 border-b border-orange-200 flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-orange-700" />
          <span className="text-sm font-semibold text-orange-900">
            {items.length} pending password reset{items.length === 1 ? "" : "s"}
          </span>
        </div>
        <ul className="divide-y divide-gray-100">
          {items.map((r) => (
            <li key={r.id} className="px-4 py-3 flex items-center gap-3" data-testid={`reset-row-${r.id}`}>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-ink truncate">{r.name || r.email}</div>
                <div className="text-xs text-gray-500 truncate">{r.email}</div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => act(r.id, "reject")} className="h-9 px-3 rounded-md text-xs font-medium bg-red-50 text-red-700 hover:bg-red-100" data-testid={`reject-reset-${r.id}`}>Reject</button>
                <button onClick={() => act(r.id, "approve")} className="h-9 px-3 rounded-md text-xs font-medium bg-green-50 text-green-700 hover:bg-green-100" data-testid={`approve-reset-${r.id}`}>Approve</button>
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function emptyEmpForm() {
  return { name: "", email: "", password: "", emp_code: "", designation: "", department: "", monthly_salary: "", joining_date: new Date().toISOString().slice(0, 10), bank_account: "", ifsc: "", elevated_roles: [], attendance_config_id: 1 };
}

function PendingSignups({ items, onChanged }) {
  const { confirm, ConfirmHost } = useConfirm();
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState(null);
  const [form, setForm] = useState({});
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  if (!items || items.length === 0) return null;

  const startApprove = (e) => {
    setTarget(e);
    setForm({
      emp_code: "",
      designation: "",
      department: "",
      monthly_salary: "",
      joining_date: e.joining_date || new Date().toISOString().slice(0, 10),
      bank_account: "",
      ifsc: "",
      elevated_roles: [],
      attendance_config_id: 1,
    });
    setErr("");
    setOpen(true);
  };

  const submitApprove = async (ev) => {
    ev.preventDefault(); setBusy(true); setErr("");
    try {
      const payload = {
        emp_code: form.emp_code?.trim() || null,
        designation: form.designation || null,
        department: form.department || null,
        monthly_salary: form.monthly_salary === "" ? null : Number(form.monthly_salary),
        joining_date: form.joining_date || null,
        bank_account: form.bank_account || null,
        ifsc: form.ifsc || null,
        elevated_roles: form.elevated_roles || [],
        attendance_config_id: Number(form.attendance_config_id) || 1,
      };
      await api.post(`/employees/${target.id}/approve`, payload);
      setOpen(false); setTarget(null); onChanged && onChanged();
    } catch (e2) { setErr(fmtErr(e2)); } finally { setBusy(false); }
  };

  const reject = async (e) => {
    const ok = await confirm({
      kind: "simple",
      title: `Reject signup from ${e.name}?`,
      body: `This will permanently delete ${e.email}'s account request. They can sign up again later.`,
      danger: true,
      confirmText: "Reject and delete",
    });
    if (!ok) return;
    try { await api.post(`/employees/${e.id}/reject`); onChanged && onChanged(); }
    catch (e2) { alert(fmtErr(e2)); }
  };

  return (
    <div className="mb-5" data-testid="pending-signups-panel">
      {ConfirmHost}
      <Card className="!p-0 overflow-hidden border-amber-200">
        <div className="px-4 py-3 bg-amber-50 border-b border-amber-200 flex items-center gap-2">
          <UserPlus className="h-4 w-4 text-amber-700" />
          <span className="text-sm font-semibold text-amber-900">
            {items.length} pending signup{items.length === 1 ? "" : "s"} awaiting your approval
          </span>
        </div>
        <ul className="divide-y divide-gray-100">
          {items.map((e) => (
            <li key={e.id} className="px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4" data-testid={`pending-row-${e.id}`}>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-ink truncate">{e.name}</div>
                <div className="text-xs text-gray-500 truncate">
                  {e.email}{e.phone ? ` • ${e.phone}` : ""}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => reject(e)}
                  className="h-9 px-3 rounded-md text-xs font-medium bg-red-50 text-red-700 hover:bg-red-100"
                  data-testid={`reject-signup-${e.id}`}
                >
                  <X className="h-3.5 w-3.5 inline-block -mt-px mr-1" />Reject
                </button>
                <button
                  onClick={() => startApprove(e)}
                  className="h-9 px-3 rounded-md text-xs font-medium bg-green-50 text-green-700 hover:bg-green-100"
                  data-testid={`approve-signup-${e.id}`}
                >
                  <Check className="h-3.5 w-3.5 inline-block -mt-px mr-1" />Approve
                </button>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Modal
        open={open}
        onClose={() => { setOpen(false); setTarget(null); }}
        title={target ? `Approve ${target.name}` : "Approve signup"}
        footer={
          <>
            <Button variant="secondary" onClick={() => { setOpen(false); setTarget(null); }}>Cancel</Button>
            <Button onClick={submitApprove} disabled={busy} data-testid="approve-signup-submit">
              {busy ? "Approving…" : "Approve & activate"}
            </Button>
          </>
        }
      >
        <form onSubmit={submitApprove} className="space-y-3">
          <p className="text-xs text-gray-500">
            Set the employee code and salary now. The employee will receive an activation email with their login.
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            <Input label="Employee code" required value={form.emp_code || ""} onChange={(e) => setForm({ ...form, emp_code: e.target.value })} placeholder="e.g. EMP001" data-testid="approve-emp-code" />
            <Input label="Monthly salary (₹)" type="number" required value={form.monthly_salary || ""} onChange={(e) => setForm({ ...form, monthly_salary: e.target.value })} data-testid="approve-emp-salary" />
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <Input label="Designation" value={form.designation || ""} onChange={(e) => setForm({ ...form, designation: e.target.value })} />
            <Input label="Department" value={form.department || ""} onChange={(e) => setForm({ ...form, department: e.target.value })} />
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <Input label="Joining date" type="date" value={form.joining_date || ""} onChange={(e) => setForm({ ...form, joining_date: e.target.value })} />
            <Input label="Bank A/C" value={form.bank_account || ""} onChange={(e) => setForm({ ...form, bank_account: e.target.value })} />
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <Input label="IFSC" value={form.ifsc || ""} onChange={(e) => setForm({ ...form, ifsc: e.target.value })} />
            <Select label="Elevated roles" multiple value={form.elevated_roles || []} onChange={(e) => setForm({ ...form, elevated_roles: Array.from(e.target.selectedOptions).map((o) => o.value) })}>
              <option value="accountant">Accountant</option>
              <option value="principal">Principal</option>
              <option value="cashier">Cashier</option>
            </Select>
          </div>
          {err && <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">{err}</div>}
        </form>
      </Modal>
    </div>
  );
}

function Leaves() {
  const [items, setItems] = useState(null);
  const load = async () => { setItems(null); try { setItems((await api.get("/leave/applications")).data); } catch { setItems([]); } };
  useEffect(() => { load(); }, []);
  const decide = async (id, decision) => {
    await api.post(`/leave/applications/${id}/decision`, { decision });
    load();
  };
  return (
    <div>
      <PageHeader title="Leave requests" subtitle="Approve or reject leave applications from your employees." />
      {items === null ? <Spinner /> : items.length === 0 ? (
        <Empty icon={Calendar} title="No leave requests yet" />
      ) : (
        <Card className="!p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs uppercase tracking-wider text-gray-500">
                <tr>
                  <th className="py-3 px-4">Employee</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Period</th>
                  <th className="py-3 px-4">Days</th>
                  <th className="py-3 px-4">Reason</th>
                  <th className="py-3 px-4">Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((l) => (
                  <tr key={l.id} className="border-t border-gray-100" data-testid={`leave-row-${l.id}`}>
                    <td className="py-3 px-4">
                      <div className="font-medium text-ink">{l.employee_name}</div>
                      <div className="text-xs text-gray-500">{l.employee_code}</div>
                    </td>
                    <td className="py-3 px-4 font-mono text-xs">{l.leave_type}</td>
                    <td className="py-3 px-4">{fmtDate(l.from_date)} → {fmtDate(l.to_date)}</td>
                    <td className="py-3 px-4 tabular">{l.days}</td>
                    <td className="py-3 px-4 text-gray-700 max-w-xs truncate">{l.reason || "—"}</td>
                    <td className="py-3 px-4">
                      {l.status === "pending" ? (
                        <div className="flex gap-1">
                          <button onClick={() => decide(l.id, "approved")} className="h-9 px-3 rounded-md text-xs font-medium bg-green-50 text-green-700 hover:bg-green-100" data-testid={`approve-${l.id}`}><Check className="h-3.5 w-3.5 inline-block -mt-px mr-1" />Approve</button>
                          <button onClick={() => decide(l.id, "rejected")} className="h-9 px-3 rounded-md text-xs font-medium bg-red-50 text-red-700 hover:bg-red-100" data-testid={`reject-${l.id}`}><X className="h-3.5 w-3.5 inline-block -mt-px mr-1" />Reject</button>
                        </div>
                      ) : (
                        <Badge tone={l.status === "approved" ? "green" : "red"}>{l.status}</Badge>
                      )}
                    </td>
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

function Payroll() {
  const [runs, setRuns] = useState(null);
  const [open, setOpen] = useState(false);
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const navigate = useNavigate();

  const load = async () => { setRuns(null); try { setRuns((await api.get("/payroll/runs")).data); } catch { setRuns([]); } };
  useEffect(() => { load(); }, []);

  const generate = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/payroll/generate", { month: Number(month), year: Number(year) });
      setOpen(false); load();
      navigate(`/employer/payroll/${data.id}`);
    } catch (e2) { setErr(fmtErr(e2)); } finally { setBusy(false); }
  };

  return (
    <div>
      <PageHeader title="Payroll" subtitle="Generate, approve and disburse monthly salaries (26-day basis)." action={<Button onClick={() => setOpen(true)} data-testid="generate-run"><Plus className="h-4 w-4" />Generate run</Button>} />
      {runs === null ? <Spinner /> : runs.length === 0 ? (
        <Empty icon={ScrollText} title="No payroll runs yet" hint="Generate a draft run for the current month." action={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Generate run</Button>} />
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {runs.map((r) => (
            <Card key={r.id} data-testid={`run-card-${r.id}`}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-semibold text-ink">{monthName(r.month)} {r.year}</div>
                  <div className="text-xs text-gray-500">{r.items_count} employees • {r.working_days}-day basis</div>
                </div>
                <Badge tone={statusTone(r.status)}>{r.status}</Badge>
              </div>
              <div className="text-xs text-gray-500 mt-3">Generated: {fmtDate(r.generated_at)}</div>
              <div className="mt-4 flex justify-end">
                <Button variant="secondary" onClick={() => navigate(`/employer/payroll/${r.id}`)} data-testid={`open-run-${r.id}`}>Open</Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="Generate payroll" footer={
        <>
          <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={generate} disabled={busy} data-testid="confirm-generate">{busy ? "Generating…" : "Generate"}</Button>
        </>
      }>
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

function PayrollRun() {
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

  const approve = async (decision) => {
    const ok = await confirm({
      kind: "password",
      title: decision === "approved" ? "Approve payroll run?" : "Reject payroll run?",
      body: decision === "approved"
        ? "Approving will lock attendance for the month and notify all employees on WhatsApp (if enabled). Re-enter your password to confirm."
        : "Rejecting will keep the run in 'rejected' state. Accountant must re-generate to retry.",
      danger: decision !== "approved",
    });
    if (!ok) return;
    await api.post(`/payroll/runs/${runId}/approve`, {
      decision,
      decided_at_local: new Date().toLocaleString(),
    });
    load();
  };
  const removeRun = async () => {
    const ok = await confirm({
      kind: "type",
      title: `Delete payroll run for ${monthName(run.month)} ${run.year}?`,
      body: "This unlocks the month, lets employees edit attendance, and lets the accountant re-generate. The current run and all its items will be deleted.",
      typeText: `${monthName(run.month)} ${run.year}`,
      danger: true,
      confirmText: "Delete payroll run",
    });
    if (!ok) return;
    await api.delete(`/payroll/runs/${runId}`);
    navigate("/employer/payroll");
  };
  const editDeduction = async (item) => {
    const v = window.prompt(`Deduction for ${item.employee_name} (₹). Note can be set later.`, item.deductions || 0);
    if (v === null) return;
    const d = Number(v);
    if (Number.isNaN(d) || d < 0) return;
    await api.put(`/payroll/items/${item.id}/deductions`, { deductions: d });
    load();
  };
  const disburse = async (item, method) => {
    await api.post(`/payroll/items/${item.id}/disburse`, { method });
    load();
  };
  const downloadSlip = async (item) => {
    const res = await api.get(`/payroll/items/${item.id}/slip`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a"); a.href = url; a.download = `slip-${item.emp_code}-${run.year}-${String(run.month).padStart(2,"0")}.pdf`; a.click(); URL.revokeObjectURL(url);
  };

  if (!run) return <Spinner />;
  const total = items.reduce((s, i) => s + (i.net_salary || 0), 0);
  return (
    <div>
      {ConfirmHost}
      <PageHeader
        title={`${monthName(run.month)} ${run.year}`}
        subtitle={`${items.length} employees • ${run.working_days}-day basis • Total ₹${fmtINR(total)}`}
        action={
          <div className="flex flex-wrap gap-2">
            {(run.status === "draft" || run.status === "pending_approval") && <>
              <Button variant="danger" onClick={() => approve("rejected")} data-testid="reject-run">Reject</Button>
              <Button onClick={() => approve("approved")} data-testid="approve-run"><Check className="h-4 w-4" />Approve</Button>
            </>}
            {(run.status === "approved" || run.status === "disbursed" || run.status === "rejected") && (
              <Button variant="danger" onClick={removeRun} data-testid="delete-run"><Trash2 className="h-4 w-4" />Delete run</Button>
            )}
            <Badge tone={statusTone(run.status)}>{run.status.replace("_", " ")}</Badge>
          </div>
        }
      />
      <Card className="!p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wider text-gray-500">
              <tr>
                <th className="py-3 px-4">Code</th>
                <th className="py-3 px-4">Employee</th>
                <th className="py-3 px-4">Present</th>
                <th className="py-3 px-4">Leaves</th>
                <th className="py-3 px-4">Payable</th>
                <th className="py-3 px-4">Gross</th>
                <th className="py-3 px-4">Deduct</th>
                <th className="py-3 px-4">Net</th>
                <th className="py-3 px-4">Disburse</th>
                <th className="py-3 px-4"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id} className="border-t border-gray-100" data-testid={`item-row-${i.id}`}>
                  <td className="py-3 px-4 font-mono text-xs">{i.emp_code}</td>
                  <td className="py-3 px-4 font-medium text-ink">{i.employee_name}</td>
                  <td className="py-3 px-4 tabular">{i.present_days}</td>
                  <td className="py-3 px-4 tabular">{i.paid_leave_days}</td>
                  <td className="py-3 px-4 tabular">{i.payable_days}</td>
                  <td className="py-3 px-4 tabular">₹{fmtINR(i.gross_salary)}</td>
                  <td className="py-3 px-4 tabular">
                    {run.status === "draft" ? (
                      <button className="text-blue-600 underline text-xs" onClick={() => editDeduction(i)} data-testid={`edit-deduct-${i.id}`}>₹{fmtINR(i.deductions || 0)}</button>
                    ) : (
                      <>₹{fmtINR(i.deductions || 0)}</>
                    )}
                  </td>
                  <td className="py-3 px-4 tabular font-semibold">₹{fmtINR(i.net_salary)}</td>
                  <td className="py-3 px-4">
                    {i.disbursement ? (
                      <Badge tone="green">{i.disbursement.method.toUpperCase()} • {i.disbursement.txn_id}</Badge>
                    ) : run.status === "approved" || run.status === "disbursed" ? (
                      <div className="flex gap-1">
                        <button onClick={() => disburse(i, "cash")} className="h-9 px-3 rounded-md text-xs font-medium bg-gray-50 hover:bg-gray-100" data-testid={`pay-cash-${i.id}`}><Banknote className="h-3.5 w-3.5 inline-block -mt-px mr-1" />Cash</button>
                        <button onClick={() => disburse(i, "online")} className="h-9 px-3 rounded-md text-xs font-medium bg-blue-50 text-blue-700 hover:bg-blue-100" data-testid={`pay-online-${i.id}`}>Online</button>
                      </div>
                    ) : (
                      <span className="text-xs text-gray-400">—</span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-right">
                    {(run.status === "approved" || run.status === "disbursed") && (
                      <button onClick={() => downloadSlip(i)} className="h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700" title="Download slip" data-testid={`slip-${i.id}`}>
                        <Download className="h-4 w-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-50 font-semibold text-ink" data-testid="payroll-totals">
              <tr className="border-t-2 border-gray-200">
                <td className="py-3 px-4" colSpan={2}>Totals ({items.length} employees)</td>
                <td className="py-3 px-4 tabular">{items.reduce((s, i) => s + (i.present_days || 0), 0)}</td>
                <td className="py-3 px-4 tabular">{items.reduce((s, i) => s + (i.paid_leave_days || 0), 0).toFixed(1)}</td>
                <td className="py-3 px-4 tabular">{items.reduce((s, i) => s + (i.payable_days || 0), 0).toFixed(1)}</td>
                <td className="py-3 px-4 tabular" data-testid="total-gross">₹{fmtINR(items.reduce((s, i) => s + (i.gross_salary || 0), 0))}</td>
                <td className="py-3 px-4 tabular text-red-700" data-testid="total-deductions">₹{fmtINR(items.reduce((s, i) => s + (i.deductions || 0), 0))}</td>
                <td className="py-3 px-4 tabular text-green-700" data-testid="total-net">₹{fmtINR(total)}</td>
                <td className="py-3 px-4"></td>
                <td className="py-3 px-4"></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </Card>
      <div className="mt-4 text-xs text-gray-500">* Online disbursement is currently <b>MOCKED</b>. Plug in RazorpayX keys later for real payouts.</div>
      <div className="mt-4 flex gap-2">
        <Button variant="ghost" onClick={() => navigate("/employer/payroll")}>← Back to runs</Button>
        {(run.status === "approved" || run.status === "disbursed") && (
          <Button variant="secondary" onClick={() => navigate(`/employer/payroll/${runId}/summary`)} data-testid="open-summary">View summary →</Button>
        )}
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

function InviteCodeCard({ signupCode }) {
  const [copied, setCopied] = useState("");
  if (!signupCode) return null;
  const link = `${window.location.origin}/signup?code=${signupCode}`;
  const copy = async (value, label) => {
    try { await navigator.clipboard.writeText(value); setCopied(label); setTimeout(() => setCopied(""), 1500); }
    catch { window.prompt("Copy this:", value); }
  };
  return (
    <Card data-testid="invite-code-card" className="border-blue-100">
      <div className="flex items-start gap-3 mb-3">
        <KeyRound className="h-5 w-5 text-blue-600 mt-0.5" />
        <div>
          <h3 className="font-semibold text-ink">Employee invite code</h3>
          <p className="text-sm text-gray-500">Share this code privately with new hires. They'll enter it on the sign-up screen — no public list of clients exposed.</p>
        </div>
      </div>
      <div className="bg-gray-50 border border-dashed border-gray-300 rounded-md px-4 py-4 text-center font-mono text-3xl tracking-[0.35em] text-ink select-all" data-testid="invite-code-value">
        {signupCode}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => copy(signupCode, "code")}
          className="h-10 inline-flex items-center justify-center gap-2 rounded-md border border-gray-200 hover:bg-gray-50 text-sm font-medium"
          data-testid="copy-invite-code"
        >
          <Copy className="h-4 w-4" />{copied === "code" ? "Copied!" : "Copy code"}
        </button>
        <button
          type="button"
          onClick={() => copy(link, "link")}
          className="h-10 inline-flex items-center justify-center gap-2 rounded-md border border-gray-200 hover:bg-gray-50 text-sm font-medium"
          data-testid="copy-invite-link"
        >
          <Link2 className="h-4 w-4" />{copied === "link" ? "Copied!" : "Copy share link"}
        </button>
      </div>
      <p className="text-xs text-gray-400 mt-3">
        This code is allotted by Super Admin and cannot be changed. Treat it like a password.
      </p>
    </Card>
  );
}


function SettingsPage() {
  const [t, setT] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => { try { setT((await api.get("/tenant/settings")).data); } catch { setT(null); } };
  useEffect(() => { load(); }, []);

  if (!t) return <Spinner />;
  const s = t.settings || {};
  const att = s.attendance || { default_config_id: 1, geo_fence: { enabled: false }, working_days_per_month: 26 };

  const save = async (payload) => {
    setBusy(true); setErr("");
    try { await api.put("/tenant/settings", payload); load(); } catch (e) { setErr(fmtErr(e)); } finally { setBusy(false); }
  };

  return (
    <div>
      <PageHeader title="Settings" subtitle={t.name} />
      <div className="space-y-4">
        <InviteCodeCard signupCode={t.signup_code} />

        <Card>
          <h3 className="font-semibold text-ink mb-3">Attendance</h3>
          <div className="grid sm:grid-cols-2 gap-3">
            <Select label="Default config" value={att.default_config_id} onChange={(e) => save({ attendance: { ...att, default_config_id: Number(e.target.value) } })}>
              <option value={1}>1 — Tap only</option>
              <option value={2}>2 — Tap + Geo Location</option>
              <option value={3}>3 — Tap + Geo Fence</option>
              <option value={4}>4 — Tap + Both</option>
              <option value={5}>5 — Facial</option>
              <option value={6}>6 — Facial + Geo Location</option>
              <option value={7}>7 — Facial + Geo Fence</option>
              <option value={8}>8 — Facial + Both</option>
            </Select>
            <Input label="Working days / month" type="number" min={20} max={31} defaultValue={att.working_days_per_month} onBlur={(e) => save({ attendance: { ...att, working_days_per_month: Number(e.target.value) } })} />
          </div>
        </Card>

        <Card>
          <h3 className="font-semibold text-ink mb-1">Geo-fence</h3>
          <p className="text-sm text-gray-500 mb-3">Restrict attendance marking to a geographic perimeter. Drag the marker, tap the map to move it, or use the slider for radius.</p>
          <label className="inline-flex items-center gap-2 mb-3">
            <input type="checkbox" checked={!!att.geo_fence?.enabled} onChange={(e) => save({ attendance: { ...att, geo_fence: { ...(att.geo_fence || {}), enabled: e.target.checked, radius_m: att.geo_fence?.radius_m || 100 } } })} data-testid="fence-toggle" />
            <span className="text-sm font-medium">Enable geo-fence</span>
          </label>
          {att.geo_fence?.enabled && (
            <GeofenceMap
              value={{
                center_lat: att.geo_fence?.center_lat,
                center_lng: att.geo_fence?.center_lng,
                radius_m: att.geo_fence?.radius_m || 100,
              }}
              onChange={(next) => save({ attendance: { ...att, geo_fence: { ...att.geo_fence, ...next } } })}
            />
          )}
        </Card>

        <Card>
          <h3 className="font-semibold text-ink mb-3">Leave types</h3>
          <LeaveTypesEditor types={s.leave_types || []} resetMonth={s.leave_reset_month || 4} onChange={(types, reset) => save({ leave_types: types, leave_reset_month: reset })} />
        </Card>

        {err && <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">{err}</div>}
        {busy && <div className="text-xs text-gray-500">Saving…</div>}
      </div>
    </div>
  );
}

function LeaveTypesEditor({ types, resetMonth, onChange }) {
  const [list, setList] = useState(types);
  const [reset, setReset] = useState(resetMonth);
  useEffect(() => { setList(types); setReset(resetMonth); }, [types, resetMonth]);

  const update = (i, patch) => {
    const next = list.map((x, idx) => idx === i ? { ...x, ...patch } : x);
    setList(next);
  };
  const add = () => setList([...list, { code: "NEW", name: "New leave", annual_quota: 0, carry_forward: false, paid: true }]);
  const remove = (i) => setList(list.filter((_, idx) => idx !== i));
  const save = () => onChange(list, Number(reset));

  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <Select label="Reset month" value={reset} onChange={(e) => setReset(Number(e.target.value))} className="max-w-xs">
          {[1,2,3,4,5,6,7,8,9,10,11,12].map((m) => <option key={m} value={m}>{monthName(m)}</option>)}
        </Select>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wider text-gray-500">
            <tr><th className="py-2 pr-3">Code</th><th className="py-2 pr-3">Name</th><th className="py-2 pr-3">Annual</th><th className="py-2 pr-3">Carry</th><th className="py-2 pr-3">Paid</th><th></th></tr>
          </thead>
          <tbody>
            {list.map((lt, i) => (
              <tr key={i} className="border-t border-gray-100">
                <td className="py-2 pr-3"><input value={lt.code} onChange={(e) => update(i, { code: e.target.value })} className="h-9 w-20 border border-gray-300 rounded-md px-2" /></td>
                <td className="py-2 pr-3"><input value={lt.name} onChange={(e) => update(i, { name: e.target.value })} className="h-9 w-full border border-gray-300 rounded-md px-2" /></td>
                <td className="py-2 pr-3"><input type="number" value={lt.annual_quota} onChange={(e) => update(i, { annual_quota: Number(e.target.value) })} className="h-9 w-20 border border-gray-300 rounded-md px-2 tabular" /></td>
                <td className="py-2 pr-3"><input type="checkbox" checked={!!lt.carry_forward} onChange={(e) => update(i, { carry_forward: e.target.checked })} /></td>
                <td className="py-2 pr-3"><input type="checkbox" checked={!!lt.paid} onChange={(e) => update(i, { paid: e.target.checked })} /></td>
                <td className="py-2"><button onClick={() => remove(i)} className="text-red-600 text-xs">Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex gap-2 mt-3">
        <Button variant="secondary" onClick={add}><Plus className="h-4 w-4" />Add type</Button>
        <Button onClick={save} data-testid="save-leave-types">Save changes</Button>
      </div>
    </div>
  );
}
