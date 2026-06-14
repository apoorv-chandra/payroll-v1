/**
 * ModuleSwitcher — kebab/3-dot menu in the top-right of each module screen.
 *
 * Renders ONLY when the logged-in user has 2+ effective features. The current
 * module is suppressed from the menu (no point showing "go to module you're
 * already in"). Otherwise the menu would just be Settings/Logout, which we
 * already surface separately in Shell.jsx.
 *
 * Anchored absolute-positioned menu below the trigger, with click-outside to
 * close. Uses lucide's `MoreVertical` for the dots — universally recognised
 * mobile-friendly affordance.
 */
import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MoreVertical, Wallet, GraduationCap } from "lucide-react";
import useFeatures from "../lib/useFeatures";

const FEATURE_ICONS = {
  payroll: Wallet,
  students: GraduationCap,
};

const FEATURE_LABELS = {
  payroll: "Payroll & Attendance",
  students: "Manage students",
};

export default function ModuleSwitcher({ currentCode }) {
  const { features } = useFeatures();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  // Hide the current module from the list — showing "go to where you are"
  // is noise.
  const others = (features || []).filter((f) => f.code !== currentCode);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (others.length === 0) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="h-10 w-10 inline-flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-700"
        title="Switch module"
        aria-label="Switch module"
        data-testid="module-switcher-trigger"
      >
        <MoreVertical className="h-4 w-4" />
      </button>
      {open && (
        <div
          className="absolute right-0 mt-1 min-w-[200px] bg-white border border-gray-200 rounded-md shadow-lg py-1 z-50"
          role="menu"
          data-testid="module-switcher-menu"
        >
          {others.map((f) => {
            const Icon = FEATURE_ICONS[f.code] || Wallet;
            const label = FEATURE_LABELS[f.code] || f.name;
            return (
              <button
                key={f.code}
                onClick={() => { setOpen(false); navigate(f.landing_path); }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-ink hover:bg-gray-50"
                role="menuitem"
                data-testid={`module-switcher-${f.code}`}
              >
                <Icon className="h-4 w-4 text-gray-500" />
                <span>{label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
