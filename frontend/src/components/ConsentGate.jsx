/* eslint-disable react/no-unescaped-entities */
import React, { useEffect, useState } from "react";
import { Button, Modal, Spinner } from "./ui/Primitives";
import PrivacyNotice from "./PrivacyNotice";
import { Shield, Check } from "lucide-react";
import { api, fmtErr } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
import { requestGeoPermission } from "../lib/permissions";

/**
 * ConsentGate — minimal, professional first-run gate.
 *
 * Accept   → all consents set true EXCEPT notifications (per spec).
 *            face_capture defaults true ONLY if employer enabled it.
 * Cancel   → confirmation modal "Are you sure? You'll be signed out." → logout.
 *
 * Granular toggles (incl. notifications) live in Settings → Privacy.
 */
export default function ConsentGate({ children }) {
  const { logout } = useAuth();
  const [state, setState] = useState(null);
  const [requiresFacial, setRequiresFacial] = useState(false);
  const [showNotice, setShowNotice] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const [p, cfg] = await Promise.all([
        api.get("/me/privacy"),
        api.get("/attendance/config").catch(() => ({ data: { requires_facial: false } })),
      ]);
      setState(p.data);
      setRequiresFacial(!!cfg.data?.requires_facial);
    } catch { setState({ needs_initial_consent: false }); }
  };
  useEffect(() => { load(); }, []);

  if (state == null) return <Spinner />;
  if (!state.needs_initial_consent) return children;

  const accept = async () => {
    setBusy(true); setErr("");
    try {
      await api.put("/me/privacy/consents", {
        consents: {
          data_processing: true,
          face_capture: requiresFacial,    // ONLY if employer enabled facial
          geo_location: true,
          whatsapp_email: false,           // per spec — opt-in later in Settings
        },
      });
      // Fire the OS-level location permission prompt right after the user
      // accepts. We don't block on the outcome — they can still grant later
      // from Settings → Privacy. This just removes the silent-deny surprise
      // when they go to mark attendance for the first time.
      requestGeoPermission().catch(() => {});
      load();
    } catch (e) { setErr(fmtErr(e)); } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-5 py-8 bg-gray-50 fade-in" data-testid="consent-gate">
      <PrivacyNotice open={showNotice} onClose={() => setShowNotice(false)} />

      <div className="max-w-md w-full bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        {/* Header */}
        <div className="px-6 pt-7 pb-5 text-center border-b border-gray-100">
          <div className="inline-flex h-14 w-14 rounded-full bg-blue-50 items-center justify-center mb-3">
            <Shield className="h-7 w-7 text-blue-600" />
          </div>
          <h2 className="font-serif text-2xl text-ink tracking-tight">Terms &amp; Privacy</h2>
          <p className="text-sm text-gray-500 mt-1.5">
            Please review and accept to continue.
          </p>
        </div>

        {/* Body — three concise points */}
        <ul className="px-6 py-5 space-y-3 text-sm text-gray-700">
          <li className="flex gap-2.5">
            <Check className="h-4 w-4 text-green-600 mt-0.5 shrink-0" />
            <span>Your data is used solely for attendance, leave and payroll.</span>
          </li>
          <li className="flex gap-2.5">
            <Check className="h-4 w-4 text-green-600 mt-0.5 shrink-0" />
            <span>Optional features {requiresFacial ? "(face, location, alerts)" : "(location, alerts)"} stay toggleable in <b>Settings → Privacy</b>.</span>
          </li>
          <li className="flex gap-2.5">
            <Check className="h-4 w-4 text-green-600 mt-0.5 shrink-0" />
            <span>We follow India&apos;s <b>DPDP Act, 2023</b>. You can export or delete your data anytime.</span>
          </li>
        </ul>

        <div className="px-6 pb-3">
          <button onClick={() => setShowNotice(true)} className="text-sm text-blue-600 underline" data-testid="open-full-notice">
            Read the full Privacy Notice →
          </button>
        </div>

        {err && (
          <div className="mx-6 mb-3 text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">{err}</div>
        )}

        {/* Footer actions */}
        <div className="px-6 pb-6 pt-2 space-y-2">
          <Button
            className="w-full !h-12"
            onClick={accept}
            disabled={busy}
            data-testid="consent-accept"
          >
            {busy ? "Saving…" : "Accept and continue"}
          </Button>
          <button
            onClick={() => setConfirmCancel(true)}
            className="w-full h-10 text-sm text-gray-500 hover:text-ink"
            data-testid="consent-cancel"
          >
            Cancel
          </button>
        </div>
      </div>

      <Modal
        open={confirmCancel}
        onClose={() => setConfirmCancel(false)}
        title="Are you sure?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmCancel(false)} data-testid="cancel-stay">
              Stay
            </Button>
            <Button variant="danger" onClick={logout} data-testid="cancel-confirm-logout">
              Yes, sign me out
            </Button>
          </>
        }
      >
        <p className="text-sm text-gray-700">
          You must accept the Terms &amp; Privacy Notice to use Payroll.
          Cancelling will sign you out — you can sign back in anytime.
        </p>
      </Modal>
    </div>
  );
}
