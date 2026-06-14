/**
 * StudentsApp — the Students module entrypoint.
 *
 * Routes (under /school):
 *   /school                — list + search + create + Sheets-config banner
 *   /school/:id            — student detail (edit fields + manage files)
 *
 * Permission: any user with `students` in their effective features. Inside,
 * employees can only see their own students; employer/super_admin see all.
 *
 * Sheets sync: handled on the backend. We show the master sheet link and a
 * configure-banner if not yet set up.
 */
import React, { useEffect, useState } from "react";
import {
  Routes, Route, useNavigate, useParams, Link, Navigate,
} from "react-router-dom";
import {
  GraduationCap, Search, Plus, Upload, Trash2, ExternalLink, ArrowLeft,
  LogOut, Settings as SettingsIcon, FileText, ImageIcon,
} from "lucide-react";

import { api, fmtErr, fmtDate } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
import useFeatures from "../lib/useFeatures";
import useConfirm from "../lib/useConfirm";
import ModuleSwitcher from "../components/ModuleSwitcher";
import {
  Button, Input, Card, Modal, Empty, Spinner, Badge, PageHeader,
} from "../components/ui/Primitives";

const FILE_SLOTS = [
  { code: "photo", label: "Photograph" },
  { code: "signature", label: "Signature" },
  { code: "tenth_marksheet", label: "10th Marksheet" },
  { code: "twelfth_marksheet", label: "12th Marksheet" },
  { code: "graduation_marksheet", label: "Graduation Marksheet" },
  { code: "pg_marksheet", label: "PG Marksheet" },
  { code: "income_certificate", label: "Income Certificate" },
  { code: "caste_certificate", label: "Caste Certificate" },
  { code: "domicile_certificate", label: "Domicile Certificate" },
  { code: "affidavit", label: "Affidavit" },
  { code: "aadhaar_front", label: "Aadhaar (Front)" },
  { code: "aadhaar_back", label: "Aadhaar (Back)" },
];

// ===========================================================================
// Top-level shell
// ===========================================================================
export default function StudentsApp() {
  const { user, logout } = useAuth();
  const { has, loading: featLoading, reload } = useFeatures();
  const navigate = useNavigate();

  // Ensure features are loaded before children render — avoids a 403 race
  // where StudentsList fires GET /api/students before the cache hydrates.
  useEffect(() => { if (featLoading) reload(); /* eslint-disable-next-line */ }, []);

  if (featLoading) {
    return <div className="min-h-screen flex items-center justify-center"><Spinner /></div>;
  }
  if (!has("students")) {
    // User landed on /school but doesn't have the module — bounce them home.
    return <Navigate to="/" replace />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-10 bg-white border-b border-gray-100">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <Link to="/school" className="flex items-center gap-2 text-ink">
            <div className="h-8 w-8 rounded-lg bg-ink/5 inline-flex items-center justify-center">
              <GraduationCap className="h-4 w-4" />
            </div>
            <span className="font-serif text-base">Students</span>
          </Link>
          <div className="flex items-center gap-1">
            <button
              onClick={() => navigate("/me/privacy")}
              className="h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700"
              title="Settings"
              data-testid="students-settings-btn"
            >
              <SettingsIcon className="h-4 w-4" />
            </button>
            <ModuleSwitcher currentCode="students" />
            <button
              onClick={async () => { await logout(); navigate("/login", { replace: true }); }}
              className="h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700"
              title="Sign out"
              data-testid="students-logout-btn"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-5 sm:py-8 pb-24" data-testid="students-app-root">
        <Routes>
          <Route index element={<StudentsList user={user} />} />
          <Route path=":id" element={<StudentDetail user={user} />} />
          <Route path="*" element={<Navigate to="/school" replace />} />
        </Routes>
      </main>
    </div>
  );
}

// ===========================================================================
// List view
// ===========================================================================
function StudentsList({ user }) {
  const [q, setQ] = useState("");
  const [data, setData] = useState({ items: [], total: 0, loading: true });
  const [showCreate, setShowCreate] = useState(false);
  const [showSheets, setShowSheets] = useState(false);
  const [sheetsInfo, setSheetsInfo] = useState(null);
  const navigate = useNavigate();

  const isAdmin = user.role === "super_admin" || user.role === "employer";

  const load = async () => {
    setData((d) => ({ ...d, loading: true }));
    try {
      const { data: r } = await api.get("/students", { params: { q, limit: 100 } });
      setData({ items: r.items, total: r.total, loading: false });
    } catch {
      setData({ items: [], total: 0, loading: false });
    }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const loadSheetsInfo = async () => {
    try {
      const { data } = await api.get("/students/_sheets/info");
      setSheetsInfo(data);
    } catch { /* noop */ }
  };
  useEffect(() => { if (isAdmin) loadSheetsInfo(); /* eslint-disable-next-line */ }, [isAdmin]);

  return (
    <>
      <PageHeader
        title="Students"
        subtitle={user.role === "employee" ? "Manage records you own." : "All student records across your school."}
        action={(
          <Button onClick={() => setShowCreate(true)} data-testid="add-student-btn">
            <Plus className="h-4 w-4" /> Add student
          </Button>
        )}
      />

      {isAdmin && sheetsInfo && (
        <SheetsBanner info={sheetsInfo} onConfigure={() => setShowSheets(true)} />
      )}

      <div className="flex items-center gap-2 mb-4">
        <div className="relative flex-1">
          <Search className="h-4 w-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            placeholder="Search by name, father's name, mobile, email…"
            className="h-11 w-full border border-gray-300 rounded-md pl-10 pr-3 bg-white outline-none focus:ring-2 focus:ring-[#2563EB]"
            data-testid="students-search"
          />
        </div>
        <Button variant="secondary" onClick={load} data-testid="students-search-btn">Search</Button>
      </div>

      {data.loading ? (
        <div className="py-10 text-center"><Spinner /></div>
      ) : data.items.length === 0 ? (
        <Empty
          icon={GraduationCap}
          title="No students yet"
          hint="Add your first student record to get started."
          action={<Button onClick={() => setShowCreate(true)} data-testid="empty-add-student-btn"><Plus className="h-4 w-4" /> Add student</Button>}
        />
      ) : (
        <Card className="!p-0">
          <ul className="divide-y divide-gray-100">
            {data.items.map((s) => (
              <li key={s.id}>
                <button
                  onClick={() => navigate(`/school/${s.id}`)}
                  data-testid={`student-row-${s.id}`}
                  className="w-full text-left px-4 sm:px-5 py-3 hover:bg-gray-50 flex items-center justify-between gap-4"
                >
                  <div className="min-w-0">
                    <div className="font-medium text-ink truncate">
                      {s.name} <span className="text-gray-400 text-sm font-normal">#{s.serial_no}</span>
                    </div>
                    <div className="text-xs text-gray-500 truncate mt-0.5">
                      {[s.fathers_name, s.mobile, s.email].filter(Boolean).join(" · ") || "—"}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {countFiles(s) > 0 && (
                      <Badge tone="blue">{countFiles(s)} file{countFiles(s) > 1 ? "s" : ""}</Badge>
                    )}
                    {isAdmin && s.owner_name && (
                      <Badge tone="neutral">{s.owner_name}</Badge>
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <StudentCreateModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onSaved={(created) => { setShowCreate(false); navigate(`/school/${created.id}`); }}
      />
      <SheetsConfigureModal
        open={showSheets}
        info={sheetsInfo}
        onClose={() => setShowSheets(false)}
        onSaved={() => { setShowSheets(false); loadSheetsInfo(); }}
      />
    </>
  );
}

function countFiles(s) {
  return Object.values(s.files || {}).filter(Boolean).length;
}

// ===========================================================================
// Sheets banner + configure
// ===========================================================================
function SheetsBanner({ info, onConfigure }) {
  const [resyncing, setResyncing] = useState(false);
  const [resyncMsg, setResyncMsg] = useState("");

  const onResync = async () => {
    setResyncing(true); setResyncMsg("");
    try {
      const { data } = await api.post("/students/_sheets/resync");
      const errs = data.errors?.length ? ` (${data.errors.length} errors)` : "";
      setResyncMsg(`Synced ${data.synced} student${data.synced === 1 ? "" : "s"}${errs}.`);
      setTimeout(() => setResyncMsg(""), 4000);
    } catch (e) {
      setResyncMsg(fmtErr(e));
    } finally { setResyncing(false); }
  };

  if (!info.configured) return null;
  if (info.master_sheet_id) {
    return (
      <div className="mb-4 rounded-lg border border-green-100 bg-green-50 p-3 sm:p-4 text-sm" data-testid="sheets-banner-ok">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="font-medium text-green-800">Google Sheets sync is active</div>
            <div className="text-green-700/80 text-xs mt-0.5">Every student change mirrors to your master sheet.</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onResync}
              disabled={resyncing}
              className="inline-flex items-center gap-1.5 h-9 px-3 rounded-md text-xs font-medium bg-white border border-green-200 hover:bg-green-100 text-green-800 disabled:opacity-50"
              data-testid="resync-sheets-btn"
            >
              {resyncing ? "Re-syncing…" : "Re-sync all"}
            </button>
            <a
              href={info.master_sheet_url}
              target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1.5 h-9 px-3 rounded-md text-xs font-medium bg-white border border-green-200 hover:bg-green-100 text-green-800"
              data-testid="open-sheet-link"
            >
              Open <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
        {resyncMsg && (
          <div className="mt-2 text-xs text-green-900/80" data-testid="resync-status">{resyncMsg}</div>
        )}
      </div>
    );
  }
  return (
    <div className="mb-4 rounded-lg border border-amber-100 bg-amber-50 p-3 sm:p-4 text-sm flex items-start justify-between gap-3" data-testid="sheets-banner-configure">
      <div>
        <div className="font-medium text-amber-900">Set up Google Sheets sync</div>
        <div className="text-amber-800/80 text-xs mt-0.5">
          Pre-create a blank spreadsheet, share it with{" "}
          <code className="bg-white px-1 py-0.5 rounded text-[11px]">{info.service_account_email}</code>{" "}
          as Editor, then paste the URL here.
        </div>
      </div>
      <Button onClick={onConfigure} variant="secondary" data-testid="configure-sheets-btn">
        Configure
      </Button>
    </div>
  );
}

function SheetsConfigureModal({ open, info, onClose, onSaved }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { if (!open) { setUrl(""); setErr(""); } }, [open]);

  const save = async () => {
    setBusy(true); setErr("");
    try {
      await api.put("/students/_sheets/configure", { url_or_id: url.trim() });
      onSaved();
    } catch (e) { setErr(fmtErr(e)); } finally { setBusy(false); }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Configure Google Sheets sync"
      footer={(
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={!url.trim() || busy} data-testid="sheets-save-btn">
            {busy ? "Verifying…" : "Save"}
          </Button>
        </>
      )}
    >
      <ol className="text-sm text-gray-600 list-decimal pl-4 space-y-1.5 mb-3">
        <li>Open <a className="text-blue-600 underline" href="https://sheets.new" target="_blank" rel="noreferrer">sheets.new</a> to create a fresh spreadsheet.</li>
        <li>Click <b>Share</b> and add this email as <b>Editor</b>:
          <div className="mt-1.5 p-2 bg-gray-50 rounded text-[12px] font-mono break-all">{info?.service_account_email}</div>
        </li>
        <li>Copy the URL from your browser and paste below.</li>
      </ol>
      <Input
        label="Spreadsheet URL or ID"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://docs.google.com/spreadsheets/d/…"
        data-testid="sheets-url-input"
      />
      {err && <div className="mt-3 text-sm text-red-700 bg-red-50 border border-red-100 rounded-md px-3 py-2" data-testid="sheets-error">{err}</div>}
    </Modal>
  );
}

// ===========================================================================
// Create modal
// ===========================================================================
function StudentCreateModal({ open, onClose, onSaved }) {
  const [form, setForm] = useState({ name: "", fathers_name: "", mobile: "", email: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { if (!open) { setForm({ name: "", fathers_name: "", mobile: "", email: "" }); setErr(""); } }, [open]);

  const save = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/students", form);
      onSaved(data);
    } catch (e) { setErr(fmtErr(e)); } finally { setBusy(false); }
  };

  const upd = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add student"
      footer={(
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={!form.name.trim() || busy} data-testid="save-student-btn">
            {busy ? "Saving…" : "Create"}
          </Button>
        </>
      )}
    >
      <p className="text-xs text-gray-500 mb-3">Quick add — full details + documents can be edited next.</p>
      <div className="grid grid-cols-1 gap-3">
        <Input label="Full name *" value={form.name} onChange={upd("name")} data-testid="new-student-name" autoFocus />
        <Input label="Father's name" value={form.fathers_name} onChange={upd("fathers_name")} data-testid="new-student-fathers" />
        <Input label="Mobile" value={form.mobile} onChange={upd("mobile")} data-testid="new-student-mobile" />
        <Input label="Email" type="email" value={form.email} onChange={upd("email")} data-testid="new-student-email" />
      </div>
      {err && <div className="mt-3 text-sm text-red-700 bg-red-50 border border-red-100 rounded-md px-3 py-2">{err}</div>}
    </Modal>
  );
}

// ===========================================================================
// Detail view — edit fields + manage files
// ===========================================================================
function StudentDetail({ user }) {
  const { id } = useParams();
  const [s, setS] = useState(null);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const navigate = useNavigate();
  const confirm = useConfirm();

  const load = async () => {
    try { const { data } = await api.get(`/students/${id}`); setS(data); }
    catch (e) { setErr(fmtErr(e)); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const onSave = async (patch) => {
    setSaving(true); setMsg("");
    try {
      const next = { ...s, ...patch };
      const { data } = await api.patch(`/students/${id}`, projectFields(next));
      setS(data); setMsg("Saved.");
      setTimeout(() => setMsg(""), 1500);
    } catch (e) { setMsg(fmtErr(e)); } finally { setSaving(false); }
  };

  const onDelete = async () => {
    const ok = await confirm({
      title: "Delete student?",
      message: `This will soft-delete ${s.name}. The Google Sheets row will be struck-through, not removed.`,
      okText: "Delete",
    });
    if (!ok) return;
    try { await api.delete(`/students/${id}`); navigate("/school"); }
    catch (e) { setMsg(fmtErr(e)); }
  };

  if (err) return <div className="text-red-700 bg-red-50 border border-red-100 rounded-md px-3 py-2">{err}</div>;
  if (!s) return <div className="py-10 text-center"><Spinner /></div>;

  return (
    <>
      <button onClick={() => navigate("/school")} className="inline-flex items-center gap-1.5 text-sm text-gray-600 hover:text-ink mb-3" data-testid="back-to-students">
        <ArrowLeft className="h-4 w-4" /> All students
      </button>
      <PageHeader
        title={s.name}
        subtitle={`#${s.serial_no} · added ${s.created_at ? fmtDate(s.created_at) : "—"}`}
        action={(
          <Button variant="danger" onClick={onDelete} data-testid="delete-student-btn">
            <Trash2 className="h-4 w-4" /> Delete
          </Button>
        )}
      />

      <EditableFields student={s} onSave={onSave} saving={saving} />

      <FilesPanel student={s} onChanged={load} />

      {msg && (
        <div className={`fixed bottom-6 right-6 text-sm rounded-md px-3 py-2 shadow-md ${msg === "Saved." ? "bg-green-50 text-green-800 border border-green-200" : "bg-red-50 text-red-700 border border-red-200"}`}>
          {msg}
        </div>
      )}
    </>
  );
}

function projectFields(s) {
  const allowed = [
    "name", "fathers_name", "mothers_name", "dob", "aadhaar",
    "mobile", "alt_mobile", "email", "category", "gender",
    "address", "city", "state", "pin",
    "tenth_pass_year", "tenth_school", "tenth_board", "tenth_percent",
    "twelfth_pass_year", "twelfth_school", "twelfth_board", "twelfth_percent",
    "grad_percent", "pg_percent", "department", "course", "subjects",
  ];
  const out = {};
  for (const k of allowed) out[k] = s[k] ?? "";
  return out;
}

function EditableFields({ student, onSave, saving }) {
  const [form, setForm] = useState(student);
  useEffect(() => { setForm(student); }, [student]);

  const u = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const dirty = JSON.stringify(projectFields(form)) !== JSON.stringify(projectFields(student));

  return (
    <Card className="mb-6">
      <h3 className="font-semibold text-ink mb-4">Profile</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Input label="Full name" value={form.name || ""} onChange={u("name")} data-testid="detail-name" />
        <Input label="Father's name" value={form.fathers_name || ""} onChange={u("fathers_name")} />
        <Input label="Mother's name" value={form.mothers_name || ""} onChange={u("mothers_name")} />
        <Input label="Date of birth" value={form.dob || ""} onChange={u("dob")} placeholder="YYYY-MM-DD" />
        <Input label="Aadhaar (12 digits — masked in lists)" value={form.aadhaar || ""} onChange={u("aadhaar")} hint={student.aadhaar_masked || ""} />
        <Input label="Mobile" value={form.mobile || ""} onChange={u("mobile")} />
        <Input label="Alt mobile" value={form.alt_mobile || ""} onChange={u("alt_mobile")} />
        <Input label="Email" type="email" value={form.email || ""} onChange={u("email")} />
        <Input label="Category" value={form.category || ""} onChange={u("category")} placeholder="General / OBC / SC / ST" />
        <Input label="Gender" value={form.gender || ""} onChange={u("gender")} />
        <Input label="Address" value={form.address || ""} onChange={u("address")} />
        <Input label="City" value={form.city || ""} onChange={u("city")} />
        <Input label="State" value={form.state || ""} onChange={u("state")} />
        <Input label="PIN" value={form.pin || ""} onChange={u("pin")} />
        <Input label="10th %" value={form.tenth_percent || ""} onChange={u("tenth_percent")} />
        <Input label="12th %" value={form.twelfth_percent || ""} onChange={u("twelfth_percent")} />
        <Input label="Graduation %" value={form.grad_percent || ""} onChange={u("grad_percent")} />
        <Input label="PG %" value={form.pg_percent || ""} onChange={u("pg_percent")} />
      </div>
      <div className="mt-4 flex justify-end">
        <Button onClick={() => onSave(form)} disabled={!dirty || saving} data-testid="save-profile-btn">
          {saving ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </Card>
  );
}

// ===========================================================================
// Files panel — one row per FILE_SLOT
// ===========================================================================
function FilesPanel({ student, onChanged }) {
  return (
    <Card>
      <h3 className="font-semibold text-ink mb-1">Documents</h3>
      <p className="text-xs text-gray-500 mb-4">
        JPEG / PNG / WEBP / PDF · up to 25 MB · auto-compressed for storage.
      </p>
      <ul className="divide-y divide-gray-100">
        {FILE_SLOTS.map((slot) => (
          <FileRow
            key={slot.code}
            slot={slot}
            file={(student.files || {})[slot.code]}
            studentId={student.id}
            onChanged={onChanged}
          />
        ))}
      </ul>
    </Card>
  );
}

function FileRow({ slot, file, studentId, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const confirm = useConfirm();
  const inputId = `file-${slot.code}`;

  const onUpload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setBusy(true); setErr("");
    try {
      const fd = new FormData();
      fd.append("file", f);
      await api.post(`/students/${studentId}/files/${slot.code}`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      onChanged();
    } catch (er) { setErr(fmtErr(er)); }
    finally { setBusy(false); e.target.value = ""; }
  };

  const onDelete = async () => {
    if (!await confirm({ title: "Delete file?", message: `Remove ${slot.label}?`, okText: "Delete" })) return;
    setBusy(true); setErr("");
    try { await api.delete(`/students/${studentId}/files/${slot.code}`); onChanged(); }
    catch (er) { setErr(fmtErr(er)); }
    finally { setBusy(false); }
  };

  const openFile = async () => {
    // Open in a new tab; backend Content-Disposition forces download for safety,
    // but image/pdf inline preview will still work because the browser respects
    // the media-type when navigating.
    const base = process.env.REACT_APP_BACKEND_URL || "";
    const token = localStorage.getItem("access_token");
    const resp = await fetch(`${base}/api/students/files/${file.file_id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) { setErr("Failed to fetch file."); return; }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    // Revoke after a delay so the new tab has time to use the URL.
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  };

  const Icon = (file?.mime || "").startsWith("image/") ? ImageIcon : FileText;

  return (
    <li className="py-3 flex items-center gap-3" data-testid={`file-row-${slot.code}`}>
      <div className="h-9 w-9 rounded-md bg-gray-100 inline-flex items-center justify-center text-gray-600 shrink-0">
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-ink">{slot.label}</div>
        <div className="text-xs text-gray-500 truncate">
          {file ? `${file.filename || "uploaded"} · ${formatBytes(file.size || 0)}` : "Not uploaded"}
        </div>
        {err && <div className="text-xs text-red-700 mt-0.5">{err}</div>}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {file ? (
          <>
            <button
              onClick={openFile}
              className="h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700"
              title="View"
              data-testid={`view-file-${slot.code}`}
            >
              <ExternalLink className="h-4 w-4" />
            </button>
            <button
              onClick={onDelete}
              disabled={busy}
              className="h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-red-50 text-red-600"
              title="Delete"
              data-testid={`delete-file-${slot.code}`}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </>
        ) : (
          <>
            <input id={inputId} type="file" className="hidden" accept="image/*,application/pdf" onChange={onUpload} data-testid={`file-input-${slot.code}`} />
            <label htmlFor={inputId} className={`inline-flex items-center gap-1.5 h-9 px-3 rounded-md text-xs font-medium bg-white border border-gray-300 hover:bg-gray-50 cursor-pointer ${busy ? "opacity-50 pointer-events-none" : ""}`} data-testid={`upload-${slot.code}`}>
              <Upload className="h-3.5 w-3.5" />
              {busy ? "Uploading…" : "Upload"}
            </label>
          </>
        )}
      </div>
    </li>
  );
}

function formatBytes(n) {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
