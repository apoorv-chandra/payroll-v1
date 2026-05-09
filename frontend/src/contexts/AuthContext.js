import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined);

  const fetchMe = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      localStorage.setItem("auth_user", JSON.stringify(data));
    } catch {
      setUser(null);
      localStorage.removeItem("auth_user");
    }
  }, []);

  useEffect(() => { fetchMe(); }, [fetchMe]);

  const login = async (email, password, captcha_token, captcha_answer) => {
    try {
      const { data } = await api.post("/auth/login", {
        email, password, captcha_token, captcha_answer,
      });
      if (data?.access_token) localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("auth_user", JSON.stringify(data.user));
      setUser(data.user);
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
