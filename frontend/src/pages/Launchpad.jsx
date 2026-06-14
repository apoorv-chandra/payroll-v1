import React from "react";
import { useNavigate, Navigate } from "react-router-dom";
import {
  Wallet, GraduationCap, LogOut, Settings as SettingsIcon, ChevronRight,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import useFeatures from "../lib/useFeatures";
import { Spinner } from "../components/ui/Primitives";
import { homeFor } from "./Login";

/**
 * Launchpad — landing for users who have access to 2+ modules.
 *
 * Users with only ONE module skip this screen entirely (Login.jsx auto-routes
 * them straight to the module's landing path). Single-module is the common
 * case today, so this page is opt-in by data.
 */

const ICONS = {
  Wallet,
  GraduationCap,
};

export default function Launchpad() {
  const { user, logout } = useAuth();
  const { loading, features } = useFeatures();
  const navigate = useNavigate();

  if (!user) return <Navigate to="/login" replace />;
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Spinner />
      </div>
    );
  }

  // Single-feature users have no business being here — bounce them home.
  if (features.length === 0) {
    return (
      <EmptyState
        userName={user.name || user.email}
        onLogout={async () => { await logout(); navigate("/login", { replace: true }); }}
      />
    );
  }
  if (features.length === 1) {
    return <Navigate to={features[0].landing_path || homeFor(user)} replace />;
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white">
      <header className="sticky top-0 z-10 bg-white/80 backdrop-blur border-b border-gray-100">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-ink text-white inline-flex items-center justify-center font-serif text-sm">P</div>
            <span className="text-sm text-gray-500">Welcome, <b className="text-ink">{user.name || user.email}</b></span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => navigate("/me/privacy")}
              className="h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700"
              title="Settings"
              data-testid="launchpad-settings"
            >
              <SettingsIcon className="h-4 w-4" />
            </button>
            <button
              onClick={async () => { await logout(); navigate("/login", { replace: true }); }}
              className="h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700"
              title="Sign out"
              data-testid="launchpad-logout"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-14">
        <div className="mb-8 sm:mb-12">
          <h1 className="font-serif text-3xl sm:text-4xl text-ink tracking-tight">Choose a module</h1>
          <p className="text-sm text-gray-500 mt-2 max-w-md">
            Your account has access to {features.length} modules. Pick one to continue — you can switch any time from the top header.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5">
          {features.map((f) => (
            <ModuleTile
              key={f.code}
              feature={f}
              onClick={() => navigate(f.landing_path)}
            />
          ))}
        </div>
      </main>
    </div>
  );
}

function ModuleTile({ feature, onClick }) {
  const Icon = ICONS[feature.icon] || Wallet;
  return (
    <button
      onClick={onClick}
      data-testid={`module-tile-${feature.code}`}
      className="group relative text-left bg-white border border-gray-200 rounded-2xl p-5 sm:p-6 hover:border-ink hover:shadow-md transition-all active:scale-[0.99]"
    >
      <div className="flex items-start justify-between mb-4">
        <div className="h-12 w-12 rounded-xl bg-ink/5 text-ink inline-flex items-center justify-center group-hover:bg-ink group-hover:text-white transition-colors">
          <Icon className="h-5 w-5" />
        </div>
        <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-ink transition-colors" />
      </div>
      <h2 className="font-serif text-xl text-ink tracking-tight">{feature.name}</h2>
      <p className="text-sm text-gray-500 mt-1.5 line-clamp-2">{feature.description}</p>
    </button>
  );
}

function EmptyState({ userName, onLogout }) {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <div className="flex-1 flex items-center justify-center px-6">
        <div className="max-w-md text-center">
          <div className="inline-flex h-12 w-12 rounded-xl bg-ink/5 text-ink items-center justify-center mb-4">
            <SettingsIcon className="h-5 w-5" />
          </div>
          <h1 className="font-serif text-2xl text-ink mb-2">No modules enabled</h1>
          <p className="text-sm text-gray-500 mb-6">
            Hi {userName}, no modules are enabled for your account yet. Please contact your administrator.
          </p>
          <button
            onClick={onLogout}
            className="h-10 px-4 rounded-md bg-ink text-white text-sm hover:opacity-90"
            data-testid="empty-logout"
          >
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
