import React, { useEffect, useState } from "react";
import { Link, useNavigate, Navigate } from "react-router-dom";
import { Eye, EyeOff, RefreshCw, Globe, Building2, Check } from "lucide-react";

import { useAuth } from "../contexts/AuthContext";
import { useI18n } from "../contexts/I18nContext";
import { Button, Input, Select, Spinner } from "../components/ui/Primitives";
import PrivacyNotice from "../components/PrivacyNotice";
import { api, fmtErr } from "../lib/api";
import { homeFor, FullScreenLoader } from "./Login";

export default function Signup() {
  const { user } = useAuth();
  const { lang, setLang } = useI18n();
  const navigate = useNavigate();

  const [tenants, setTenants] = useState(null);
  const [tenantId, setTenantId] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [consent, setConsent] = useState(false);
  const [showPrivacy, setShowPrivacy] = useState(false);
  const [cap, setCap] = useState(null);
  const [capAns, setCapAns] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(null); // { tenant_name, message }

  const loadCaptcha = async () => {
    try {
      const { data } = await api.get("/auth/captcha");
      setCap(data); setCapAns("");
    } catch { /* noop */ }
  };

  useEffect(() => {
    loadCaptcha();
    api.get("/auth/employers")
      .then((r) => setTenants(r.data || []))
      .catch(() => setTenants([]));
  }, []);

  if (user === undefined) return <FullScreenLoader />;
  if (user) return <Navigate to={homeFor(user)} replace />;

  const onSubmit = async (e) => {
    e.preventDefault();
    setErr("");
    if (!tenantId) return setErr("Please choose your employer.");
    if (!consent) return setErr("Please accept the Privacy Notice to continue.");
    if (password.length < 6) return setErr("Password must be at least 6 characters.");
    setBusy(true);
    try {
      const { data } = await api.post("/auth/signup", {
        tenant_id: tenantId,
        name: name.trim(),
        email: email.trim().toLowerCase(),
        phone: phone.trim() || null,
        password,
        consent: true,
        captcha_token: cap?.token,
        captcha_answer: Number(capAns),
      });
      setDone(data);
    } catch (e2) {
      setErr(fmtErr(e2));
      loadCaptcha();
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div className="min-h-screen flex flex-col safe-top safe-bottom bg-white">
        <div className="flex-1 flex items-center justify-center px-5">
          <div className="w-full max-w-md text-center fade-in" data-testid="signup-success">
            <div className="inline-flex h-14 w-14 rounded-full bg-green-50 items-center justify-center mx-auto mb-4">
              <Check className="h-7 w-7 text-green-600" />
            </div>
            <h1 className="font-serif text-3xl text-ink tracking-tight">Request sent</h1>
            <p className="text-sm text-gray-600 mt-3">
              {done.message || `We've sent your request to ${done.tenant_name}. You'll be able to sign in once they approve it.`}
            </p>
            <div className="mt-8 flex flex-col gap-2">
              <Button onClick={() => navigate("/login")} data-testid="signup-back-to-login">
                Back to sign in
              </Button>
              <button
                type="button"
                onClick={() => { setDone(null); setName(""); setEmail(""); setPhone(""); setPassword(""); setConsent(false); loadCaptcha(); }}
                className="text-sm text-gray-500 hover:text-ink"
                data-testid="signup-another"
              >
                Sign up another employee
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col safe-top safe-bottom bg-white">
      <div className="absolute top-3 right-3 z-10">
        <button
          type="button"
          onClick={() => setLang(lang === "hi" ? "en" : "hi")}
          className="inline-flex items-center gap-1.5 h-10 px-3 rounded-full border border-gray-200 bg-white text-sm font-medium hover:bg-gray-50"
          data-testid="lang-toggle-signup"
        >
          <Globe className="h-4 w-4" />
          {lang === "hi" ? "हिं" : "EN"}
        </button>
      </div>

      <div className="flex-1 flex items-center justify-center px-5 py-8">
        <div className="w-full max-w-md fade-in">
          <div className="mb-7 sm:mb-8 text-center">
            <div className="inline-flex h-12 w-12 rounded-xl bg-ink text-white items-center justify-center mb-4">
              <Building2 className="h-5 w-5" />
            </div>
            <h1 className="font-serif text-3xl sm:text-4xl text-ink tracking-tight">Join your workplace</h1>
            <p className="text-sm text-gray-500 mt-2">Create your employee account — your employer approves it from their dashboard.</p>
          </div>

          <form onSubmit={onSubmit} className="space-y-3.5" data-testid="signup-form">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Employer</label>
              {tenants === null ? (
                <div className="h-12 rounded-md border border-gray-200 bg-gray-50 flex items-center px-3 text-sm text-gray-500">
                  <Spinner className="!h-4 !w-4 mr-2" /> Loading employers…
                </div>
              ) : tenants.length === 0 ? (
                <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">
                  No employers are accepting signups yet. Ask your employer to register first.
                </div>
              ) : (
                <Select
                  required
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  data-testid="signup-employer"
                >
                  <option value="">— Choose your employer —</option>
                  {tenants.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </Select>
              )}
            </div>

            <Input
              label="Full name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="As it appears on your bank account"
              data-testid="signup-name"
            />

            <Input
              label="Work email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              data-testid="signup-email"
            />

            <Input
              label="Phone (optional, for WhatsApp alerts)"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+91…"
              data-testid="signup-phone"
            />

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Choose a password</label>
              <div className="relative">
                <input
                  type={showPwd ? "text" : "password"}
                  autoComplete="new-password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-12 w-full border border-gray-300 rounded-md px-4 pr-12 outline-none bg-white focus:ring-2 focus:ring-[#2563EB] focus:border-transparent"
                  placeholder="At least 6 characters"
                  data-testid="signup-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPwd((s) => !s)}
                  className="absolute right-1 top-1/2 -translate-y-1/2 h-10 w-10 inline-flex items-center justify-center text-gray-500 hover:text-ink"
                  data-testid="signup-toggle-password"
                >
                  {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Quick maths check</label>
              <div className="flex items-center gap-2">
                <div
                  className="select-none h-12 px-4 rounded-md bg-gray-50 border border-dashed border-gray-300 inline-flex items-center font-mono tracking-widest text-base"
                  style={{ letterSpacing: "0.25em", fontStyle: "italic", textShadow: "1px 1px 0 #E5E7EB" }}
                >
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
                  data-testid="signup-captcha"
                />
                <button
                  type="button"
                  onClick={loadCaptcha}
                  className="h-12 w-12 inline-flex items-center justify-center rounded-md border border-gray-300 hover:bg-gray-50"
                  title="Refresh"
                  data-testid="signup-captcha-refresh"
                >
                  <RefreshCw className="h-4 w-4" />
                </button>
              </div>
            </div>

            <label className="flex items-start gap-3 pt-1 cursor-pointer" data-testid="signup-consent-row">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-[#2563EB]"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                data-testid="signup-consent"
              />
              <span className="text-sm text-gray-700 leading-5">
                I have read and accept the{" "}
                <button
                  type="button"
                  onClick={() => setShowPrivacy(true)}
                  className="text-blue-600 underline"
                  data-testid="signup-open-privacy"
                >
                  Privacy Notice (DPDP)
                </button>{" "}
                and consent to processing my data for attendance, leave and payroll.
              </span>
            </label>

            {err && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2" data-testid="signup-error">
                {err}
              </div>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={busy || !tenants || tenants.length === 0}
              data-testid="signup-submit"
            >
              {busy ? "Sending request…" : "Request access"}
            </Button>

            <p className="text-center text-sm text-gray-500 pt-1">
              Already have an account?{" "}
              <Link to="/login" className="text-blue-600 underline" data-testid="signup-login-link">
                Sign in
              </Link>
            </p>
          </form>
        </div>
      </div>

      <footer className="text-center text-xs text-gray-400 py-4">
        Payroll & Attendance — DPDP-aware multi-tenant platform
      </footer>

      <PrivacyNotice open={showPrivacy} onClose={() => setShowPrivacy(false)} />
    </div>
  );
}
