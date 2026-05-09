import React from "react";

export function Button({ as: Tag = "button", variant = "primary", className = "", children, ...rest }) {
  const base = "inline-flex items-center justify-center gap-2 h-12 px-5 rounded-md font-medium transition-opacity duration-150 disabled:opacity-50";
  const variants = {
    primary: "bg-[#2563EB] text-white hover:bg-[#1D4ED8]",
    secondary: "bg-white text-ink border border-gray-300 hover:bg-gray-50",
    ghost: "bg-transparent text-gray-800 hover:bg-gray-100",
    danger: "bg-white text-red-600 border border-red-200 hover:bg-red-50",
    dark: "bg-ink text-white hover:bg-black",
  };
  return (
    <Tag className={`${base} ${variants[variant] || variants.primary} ${className}`} {...rest}>
      {children}
    </Tag>
  );
}

export function Input({ label, hint, error, className = "", ...rest }) {
  return (
    <label className="block w-full">
      {label && <span className="block text-sm font-medium text-gray-700 mb-1">{label}</span>}
      <input
        className={`h-12 w-full border ${error ? "border-red-400" : "border-gray-300"} rounded-md px-4 outline-none bg-white focus:ring-2 focus:ring-[#2563EB] focus:border-transparent ${className}`}
        {...rest}
      />
      {hint && !error && <span className="block text-xs text-gray-500 mt-1">{hint}</span>}
      {error && <span className="block text-xs text-red-600 mt-1">{error}</span>}
    </label>
  );
}

export function Select({ label, children, error, className = "", ...rest }) {
  return (
    <label className="block w-full">
      {label && <span className="block text-sm font-medium text-gray-700 mb-1">{label}</span>}
      <select
        className={`h-12 w-full border ${error ? "border-red-400" : "border-gray-300"} rounded-md px-3 bg-white outline-none focus:ring-2 focus:ring-[#2563EB] ${className}`}
        {...rest}
      >
        {children}
      </select>
      {error && <span className="block text-xs text-red-600 mt-1">{error}</span>}
    </label>
  );
}

export function Card({ children, className = "", ...rest }) {
  return (
    <div className={`card p-4 sm:p-6 shadow-sm ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function Badge({ tone = "neutral", children }) {
  const tones = {
    neutral: "bg-gray-100 text-gray-700",
    blue: "bg-blue-50 text-blue-700",
    green: "bg-green-50 text-green-700",
    red: "bg-red-50 text-red-700",
    yellow: "bg-yellow-50 text-yellow-700",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${tones[tone] || tones.neutral}`}>
      {children}
    </span>
  );
}

export function Empty({ icon: Icon, title, hint, action }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-12 px-4">
      {Icon && (
        <div className="h-14 w-14 rounded-full bg-gray-100 flex items-center justify-center mb-4">
          <Icon className="h-6 w-6 text-gray-500" />
        </div>
      )}
      <h3 className="text-base font-medium text-ink">{title}</h3>
      {hint && <p className="text-sm text-gray-500 mt-1 max-w-md">{hint}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Modal({ open, onClose, title, children, footer }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center bg-black/40 fade-in" onClick={onClose} data-testid="modal-overlay">
      <div className="bg-white w-full sm:max-w-lg sm:rounded-2xl rounded-t-2xl shadow-xl border border-gray-200 max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 pt-4 pb-3 border-b border-gray-100 flex items-center justify-between">
          <h3 className="font-semibold text-ink">{title}</h3>
          <button data-testid="modal-close" onClick={onClose} className="text-gray-500 hover:text-ink h-9 w-9 rounded-md hover:bg-gray-100">×</button>
        </div>
        <div className="px-5 py-4 overflow-y-auto">{children}</div>
        {footer && <div className="px-5 py-3 border-t border-gray-100 flex gap-2 justify-end safe-bottom">{footer}</div>}
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-start justify-between gap-3 mb-5">
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Spinner({ className = "" }) {
  return (
    <div className={`inline-block h-5 w-5 border-2 border-gray-200 border-t-[#2563EB] rounded-full animate-spin ${className}`} />
  );
}

export function StatTile({ label, value, hint, icon: Icon }) {
  return (
    <div className="card p-4 sm:p-5 flex items-center gap-4">
      {Icon && (
        <div className="h-10 w-10 rounded-lg bg-blue-50 flex items-center justify-center text-[#2563EB] shrink-0">
          <Icon className="h-5 w-5" />
        </div>
      )}
      <div className="min-w-0">
        <div className="text-xs uppercase tracking-widest text-gray-500">{label}</div>
        <div className="text-xl font-semibold text-ink tabular truncate">{value}</div>
        {hint && <div className="text-xs text-gray-500 mt-0.5">{hint}</div>}
      </div>
    </div>
  );
}
