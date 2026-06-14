import React, { useEffect, useState } from "react";
import { Link, useNavigate, Navigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useI18n } from "../contexts/I18nContext";
import { Button, Input, Spinner, Modal } from "../components/ui/Primitives";
import { Eye, EyeOff, RefreshCw, Globe, Mail } from "lucide-react";
import { api, fmtErr } from "../lib/api";
import { loadFeatures, resetFeatures } from "../lib/useFeatures";

export default function Login() {
  const { user, login } = useAuth();
  const { t, lang, setLang } = useI18n();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [cap, setCap] = useState(null);
  const [capAns, setCapAns] = useState("");
  const [showForgot, setShowForgot] = useState(false);

  const loadCaptcha = async () => {
    try {
      const { data } = await api.get("/auth/captcha");
      setCap(data); setCapAns("");
    } catch {/* noop */}
  };
  useEffect(() => { loadCaptcha(); }, []);

  if (user === undefined) return <FullScreenLoader />;
  // If already logged in, send to launchpad — it handles 0/1/many feature redirect.
  if (user) return <Navigate to="/launchpad" replace />;

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const u = await login(email.trim(), password, cap?.token, Number(capAns));
      // Fetch effective features to decide where to land.
      //  • 0 features → empty-state Launchpad (user contacts admin).
      //  • 1 feature  → straight into that module (single-feature users skip the picker).
      //  • 2+ features → /launchpad tile picker.
      resetFeatures();
      const feats = await loadFeatures(true);
      const list = feats?.features || [];
      if (list.length === 1) {
        navigate(list[0].landing_path || homeFor(u), { replace: true });
      } else if (list.length >= 2) {
        navigate("/launchpad", { replace: true });
      } else {
        // No active modules — show launchpad's empty state for clarity.
        navigate("/launchpad", { replace: true });
      }
    } catch (e2) {
      setErr(e2.message);
      loadCaptcha();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col safe-top safe-bottom bg-white">
      <div className="absolute top-3 right-3 z-10">
        <button
          type="button"
          onClick={() => setLang(lang === "hi" ? "en" : "hi")}
          className="inline-flex items-center gap-1.5 h-10 px-3 rounded-full border border-gray-200 bg-white text-sm font-medium hover:bg-gray-50"
          data-testid="lang-toggle-login"
        >
          <Globe className="h-4 w-4" />
          {lang === "hi" ? "हिं" : "EN"}
        </button>
      </div>
      <div className="flex-1 flex items-center justify-center px-5">
        <div className="w-full max-w-md fade-in">
          <div className="mb-8 sm:mb-10 text-center">
            <div className="inline-flex h-12 w-12 rounded-xl bg-ink text-white items-center justify-center font-serif text-lg mb-4">P</div>
            <h1 className="font-serif text-3xl sm:text-4xl text-ink tracking-tight">{t("login.title")}</h1>
            <p className="text-sm text-gray-500 mt-2">{t("login.sub")}</p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" data-testid="login-form">
            <Input
              label={t("login.email")}
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              data-testid="login-email"
            />
            <div>
              <span className="block text-sm font-medium text-gray-700 mb-1">{t("login.password")}</span>
              <div className="relative">
                <input
                  type={showPwd ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-12 w-full border border-gray-300 rounded-md px-4 pr-12 outline-none bg-white focus:ring-2 focus:ring-[#2563EB] focus:border-transparent"
                  placeholder="••••••••"
                  data-testid="login-password"
                />
                <button type="button" onClick={() => setShowPwd((s) => !s)} className="absolute right-1 top-1/2 -translate-y-1/2 h-10 w-10 inline-flex items-center justify-center text-gray-500 hover:text-ink" data-testid="login-toggle-password">
                  {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div>
              <span className="block text-sm font-medium text-gray-700 mb-1">{t("login.captcha_q")}</span>
              <div className="flex items-center gap-2">
                <div className="select-none h-12 px-4 rounded-md bg-gray-50 border border-dashed border-gray-300 inline-flex items-center font-mono tracking-widest text-base"
                     style={{ letterSpacing: "0.25em", fontStyle: "italic", textShadow: "1px 1px 0 #E5E7EB" }}>
                  {cap ? `${cap.a} ${cap.op} ${cap.b} = ?` : "—"}
                </div>
                <input
                  type="number"
                  required
                  inputMode="numeric"
                  value={capAns}
                  onChange={(e) => setCapAns(e.target.value)}
                  className="h-12 w-24 border border-gray-300 rounded-md px-3 text-center outline-none bg-white focus:ring-2 focus:ring-[#2563EB]"
                  placeholder="?"
                  data-testid="login-captcha"
                />
                <button type="button" onClick={loadCaptcha} className="h-12 w-12 inline-flex items-center justify-center rounded-md border border-gray-300 hover:bg-gray-50" title={t("login.captcha_refresh")} data-testid="login-captcha-refresh">
                  <RefreshCw className="h-4 w-4" />
                </button>
              </div>
            </div>

            {err && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2" data-testid="login-error">{err}</div>
            )}

            <Button type="submit" className="w-full" disabled={busy} data-testid="login-submit">
              {busy ? t("common.signing_in") : t("common.sign_in")}
            </Button>

            <div className="text-center pt-1">
              <button
                type="button"
                onClick={() => setShowForgot(true)}
                className="text-sm text-gray-500 hover:text-blue-600"
                data-testid="forgot-password-link"
              >
                Forgot password?
              </button>
            </div>

            <p className="text-center text-sm text-gray-500 pt-1">
              New employee?{" "}
              <Link to="/signup" className="text-blue-600 underline" data-testid="login-signup-link">
                Sign up to join your employer
              </Link>
            </p>
          </form>
        </div>
      </div>

      <ForgotPasswordModal open={showForgot} onClose={() => setShowForgot(false)} />

      <footer className="text-center text-xs text-gray-400 py-4">
        <strong className="text-gray-500">PAYROLL</strong> · powered by Noratech Private Limited
      </footer>
    </div>
  );
}

function ForgotPasswordModal({ open, onClose }) {
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState({ kind: "", text: "" });

  useEffect(() => {
    if (!open) { setEmail(""); setPw(""); setMsg({ kind: "", text: "" }); }
  }, [open]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setMsg({ kind: "", text: "" });
    try {
      const { data } = await api.post("/auth/forgot-password", { email: email.trim().toLowerCase(), new_password: pw });
      setMsg({ kind: "ok", text: data?.message || "Request sent. Your employer will approve it." });
    } catch (e2) { setMsg({ kind: "err", text: fmtErr(e2) }); }
    finally { setBusy(false); }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Reset your password"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Close</Button>
          {msg.kind !== "ok" && (
            <Button onClick={submit} disabled={busy || !email || pw.length < 6} data-testid="forgot-submit">
              {busy ? "Sending…" : "Send request"}
            </Button>
          )}
        </>
      }
    >
      <p className="text-sm text-gray-600 mb-3">
        Enter your email and a new password. Your employer will get a request to approve the change — once they confirm, you can sign in with the new password.
      </p>
      <form onSubmit={submit} className="space-y-2.5">
        <Input
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          data-testid="forgot-email"
        />
        <Input
          type="password"
          autoComplete="new-password"
          required
          minLength={6}
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          placeholder="New password (min 6 chars)"
          data-testid="forgot-new-password"
        />
      </form>
      {msg.text && (
        <div className={`mt-3 text-sm rounded-md px-3 py-2 ${msg.kind === "ok" ? "bg-green-50 text-green-800 border border-green-100" : "bg-red-50 text-red-700 border border-red-100"}`}>
          <Mail className="h-4 w-4 inline-block -mt-px mr-1" />{msg.text}
        </div>
      )}
    </Modal>
  );
}

export function FullScreenLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-white">
      <Spinner className="!h-8 !w-8" />
    </div>
  );
}

export function homeFor(u) {
  if (!u) return "/login";
  if (u.role === "super_admin") return "/admin";
  if (u.role === "employer") return "/employer";
  if (u.role === "employee" && (u.elevated_roles || []).includes("accountant")) return "/me";
  return "/me";
}
