import axios from "axios";

const BASE = process.env.REACT_APP_BACKEND_URL;

export const api = axios.create({
  baseURL: `${BASE}/api`,
  withCredentials: true,
});

// Attach token from localStorage too (cookie + bearer for safety)
api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("access_token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

export function fmtINR(n) {
  if (n == null || isNaN(Number(n))) return "—";
  try {
    return Number(n).toLocaleString("en-IN", {
      maximumFractionDigits: 2,
      minimumFractionDigits: 2,
    });
  } catch {
    return String(n);
  }
}

export function fmtErr(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(", ");
  if (d?.msg) return d.msg;
  return e?.message || "Something went wrong";
}

export function monthName(m) {
  return ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][m] || "";
}

export function monthShort(m) {
  return ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m] || "";
}

export function fmtDate(s) {
  if (!s) return "—";
  try {
    const d = new Date(s);
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return s;
  }
}

export function fmtTime(s) {
  if (!s) return "—";
  try {
    const d = new Date(s);
    return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return s;
  }
}
