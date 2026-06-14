import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useI18n } from "../contexts/I18nContext";
import { LogOut, Globe, Settings as SettingsIcon } from "lucide-react";
import ModuleSwitcher from "./ModuleSwitcher";

export default function Shell({ children, nav }) {
  const { user, logout } = useAuth();
  const { lang, setLang } = useI18n();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const toggleLang = () => setLang(lang === "hi" ? "en" : "hi");

  // The "settings" tab lives at a different path per role.
  // - employees: /me/privacy (DPDP toggles, location list, password)
  // - employers / super_admin: /employer/settings or /admin (best-effort)
  const settingsPath =
    user?.role === "employee"
      ? "/me/privacy"
      : user?.role === "employer"
      ? "/employer/settings"
      : "/admin";
  const goSettings = () => navigate(settingsPath);

  return (
    <div className="min-h-screen bg-[#F9FAFB]">
      {/* Top bar */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-30 safe-top">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-md bg-ink text-white flex items-center justify-center font-serif font-semibold">P</div>
            <div className="leading-tight">
              <div className="text-sm font-semibold text-ink">Payroll</div>
              <div className="text-[10px] uppercase tracking-widest text-gray-500">{labelForRole(user)}</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Desktop links */}
            <nav className="hidden md:flex items-center gap-1">
              {nav.map((it) => (
                <NavLink
                  key={it.to}
                  to={it.to}
                  end={it.end}
                  data-testid={`nav-${it.id}`}
                  className={({ isActive }) =>
                    `px-3 h-10 inline-flex items-center rounded-md text-sm font-medium ${isActive ? "bg-blue-50 text-[#2563EB]" : "text-gray-700 hover:bg-gray-100"}`
                  }
                >
                  {it.label}
                </NavLink>
              ))}
            </nav>
            <div className="hidden sm:flex items-center gap-2 pl-3 border-l border-gray-200">
              <div className="text-right leading-tight">
                <div className="text-sm font-medium text-ink truncate max-w-[180px]">{user?.name}</div>
                <div className="text-[11px] text-gray-500 truncate max-w-[180px]">{user?.email}</div>
              </div>
              <button data-testid="lang-toggle" onClick={toggleLang} className="h-10 w-10 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700" title="Language">
                <Globe className="h-4 w-4" />
              </button>
              <button data-testid="settings-button" onClick={goSettings} className="h-10 w-10 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700" title="Settings">
                <SettingsIcon className="h-4 w-4" />
              </button>
              <ModuleSwitcher currentCode="payroll" />
              <button data-testid="logout-button" onClick={onLogout} className="h-10 w-10 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700">
                <LogOut className="h-4 w-4" />
              </button>
            </div>
            <button data-testid="lang-toggle-mobile" onClick={toggleLang} className="sm:hidden h-10 w-10 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700">
              <Globe className="h-4 w-4" />
            </button>
            <button data-testid="settings-button-mobile" onClick={goSettings} className="sm:hidden h-10 w-10 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700" title="Settings" aria-label="Open settings">
              <SettingsIcon className="h-5 w-5" />
            </button>
            <div className="sm:hidden inline-flex"><ModuleSwitcher currentCode="payroll" /></div>
            <button data-testid="logout-button-mobile" onClick={onLogout} className="sm:hidden h-10 w-10 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-5 pb-bottom-nav md:pb-8 fade-in">
        {children}
      </main>

      {/* Bottom nav (mobile only) */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 bg-white border-t border-gray-200 z-40 safe-bottom" data-testid="bottom-nav">
        <ul className="grid" style={{ gridTemplateColumns: `repeat(${nav.length}, minmax(0, 1fr))` }}>
          {nav.map((it) => (
            <li key={it.to}>
              <NavLink
                to={it.to}
                end={it.end}
                data-testid={`bnav-${it.id}`}
                className={({ isActive }) =>
                  `flex flex-col items-center justify-center h-16 text-[11px] ${isActive ? "text-[#2563EB]" : "text-gray-600"}`
                }
              >
                {({ isActive }) => (
                  <>
                    <it.icon className={`h-5 w-5 mb-0.5 ${isActive ? "text-[#2563EB]" : "text-gray-500"}`} />
                    <span className="font-medium">{it.label}</span>
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}

function labelForRole(u) {
  if (!u) return "";
  if (u.role === "super_admin") return "Super Admin";
  if (u.role === "employer") return "Employer";
  return "Employee";
}
