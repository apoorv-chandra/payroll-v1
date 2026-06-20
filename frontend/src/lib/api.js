import axios from "axios";

const BASE = process.env.REACT_APP_BACKEND_URL;

// `withCredentials: false` is intentional. Auth flows through the Bearer
// token attached below by the request interceptor; the cookie that
// /api/auth/login sets is a vestigial secondary mechanism kept only for
// same-origin browser users. Sending credentials cross-origin would force
// the response to include `Access-Control-Allow-Origin: <exact-origin>`
// (the spec forbids `*` with credentials), which the upstream proxy /
// edge CDN doesn't always honour — and that breaks the Capacitor APK
// where the WebView origin (`https://localhost`) is cross-origin to the
// backend host. Bearer-only sidesteps that whole class of failures.
export const api = axios.create({
  baseURL: `${BASE}/api`,
  withCredentials: false,
});

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
