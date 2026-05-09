import React, { useState } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { Button, Input } from "../components/ui/Primitives";
import { Eye, EyeOff } from "lucide-react";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (user === undefined) return <FullScreenLoader />;
  if (user) return <Navigate to={homeFor(user)} replace />;

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const u = await login(email.trim(), password);
      navigate(homeFor(u), { replace: true });
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col safe-top safe-bottom bg-white">
      <div className="flex-1 flex items-center justify-center px-5">
        <div className="w-full max-w-md fade-in">
          <div className="mb-8 sm:mb-10 text-center">
            <div className="inline-flex h-12 w-12 rounded-xl bg-ink text-white items-center justify-center font-serif text-lg mb-4">P</div>
            <h1 className="font-serif text-3xl sm:text-4xl text-ink tracking-tight">Welcome back</h1>
            <p className="text-sm text-gray-500 mt-2">Sign in to manage attendance, leaves & payroll.</p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" data-testid="login-form">
            <Input
              label="Email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              data-testid="login-email"
            />
            <div>
              <label className="block w-full">
                <span className="block text-sm font-medium text-gray-700 mb-1">Password</span>
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
              </label>
            </div>

            {err && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2" data-testid="login-error">
                {err}
              </div>
            )}

            <Button type="submit" className="w-full" disabled={busy} data-testid="login-submit">
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <div className="mt-8 border-t border-gray-100 pt-5">
            <p className="text-xs uppercase tracking-widest text-gray-500 mb-2">Demo credentials</p>
            <div className="text-sm text-gray-700">
              <div><span className="text-gray-500">Super Admin:</span> admin@payroll.app / admin123</div>
              <div className="text-xs text-gray-500 mt-1">Create an employer (tenant) from the Super Admin dashboard, then sign in as the employer to add employees.</div>
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
      <div className="h-8 w-8 border-2 border-gray-200 border-t-[#2563EB] rounded-full animate-spin" />
    </div>
  );
}

export function homeFor(u) {
  if (!u) return "/login";
  if (u.role === "super_admin") return "/admin";
  if (u.role === "employer") return "/employer";
  return "/me";
}
