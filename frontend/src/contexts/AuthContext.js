import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import { clearAuthBlock } from "../lib/offlineQueue";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  // Hydrate from localStorage immediately so the app renders without waiting
  // for a network round-trip. /auth/me is then validated in the background;
  // a 401 will log out gracefully.
  const cachedUser = (() => {
    try {
      const raw = localStorage.getItem("auth_user");
      const tok = localStorage.getItem("access_token");
      if (raw && tok) return JSON.parse(raw);
    } catch { /* noop */ }
    return undefined;
  })();
  const [user, setUser] = useState(cachedUser);

  const fetchMe = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      localStorage.setItem("auth_user", JSON.stringify(data));
    } catch (e) {
      // Only log out on a real auth rejection — not on transient network blips.
      if (e?.response?.status === 401) {
        setUser(null);
        localStorage.removeItem("auth_user");
        localStorage.removeItem("access_token");
      } else if (cachedUser === undefined) {
        // No cache and request failed → safest to show login.
        setUser(null);
      }
      // else keep cachedUser; periodic check will retry.
    }
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchMe(); }, [fetchMe]);

  const login = async (email, password, captcha_token, captcha_answer) => {
    try {
      const { data } = await api.post("/auth/login", {
        email, password, captcha_token, captcha_answer,
      });
      if (data?.access_token) localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("auth_user", JSON.stringify(data.user));
      setUser(data.user);
      // Unblock any queued attendance marks that were paused waiting for fresh auth.
      try { await clearAuthBlock(); } catch { /* noop */ }
      return data.user;
    } catch (e) {
      const d = e?.response?.data?.detail;
      const msg = typeof d === "string" ? d : (Array.isArray(d) ? d.map((x) => x.msg).join(", ") : "Sign-in failed");
      throw new Error(msg);
    }
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch { /* noop */ }
    localStorage.removeItem("access_token");
    localStorage.removeItem("auth_user");
    setUser(null);
  };

  return (
    <AuthCtx.Provider value={{ user, login, logout, refresh: fetchMe }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  return useContext(AuthCtx);
}
