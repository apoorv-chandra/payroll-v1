import React, { useEffect, useState } from "react";
import { Link, useNavigate, Navigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useI18n } from "../contexts/I18nContext";
import { Button, Input, Spinner } from "../components/ui/Primitives";
import { Eye, EyeOff, RefreshCw, Globe } from "lucide-react";
import { api } from "../lib/api";

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

  const loadCaptcha = async () => {
    try {
      const { data } = await api.get("/auth/captcha");
      setCap(data); setCapAns("");
    } catch {/* noop */}
  };
  useEffect(() => { loadCaptcha(); }, []);

  if (user === undefined) return <FullScreenLoader />;
  if (user) return <Navigate to={homeFor(user)} replace />;

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const u = await login(email.trim(), password, cap?.token, Number(capAns));
      navigate(homeFor(u), { replace: true });
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

            <p className="text-center text-sm text-gray-500 pt-1">
              New employee?{" "}
              <Link to="/signup" className="text-blue-600 underline" data-testid="login-signup-link">
                Sign up to join your employer
              </Link>
            </p>
          </form>

          <div className="mt-8 border-t border-gray-100 pt-5">
            <p className="text-xs uppercase tracking-widest text-gray-500 mb-2">{t("login.demo_creds")}</p>
            <div className="text-sm text-gray-700">
              <div><span className="text-gray-500">{t("login.super_admin")}:</span> admin@payroll.app / admin123</div>
            </div>
          </div>
        </div>
      </div>

      <footer className="text-center text-xs text-gray-400 py-4">
        Payroll & Attendance — DPDP-aware multi-tenant platform
      </footer>
    </div>
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
