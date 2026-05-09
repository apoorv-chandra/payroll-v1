import React, { useEffect, useState } from "react";
import { Button, Card, Modal, Badge, Spinner } from "./ui/Primitives";
import PrivacyNotice from "./PrivacyNotice";
import { api, fmtErr, fmtDate } from "../lib/api";

const LABELS = {
  data_processing: { name: "Use of my data for payroll & attendance", required: true,
                     desc: "Required to use the app. Without this, the platform cannot serve you." },
  face_capture: { name: "Face capture for attendance", required: false,
                  desc: "Used during check-in/out to confirm it's really you. We store only a one-way hash, never the raw image." },
  geo_location: { name: "Location sharing for attendance", required: false,
                  desc: "Used during check-in/out to honour the geo-fence set by your employer." },
  whatsapp_email: { name: "Notifications by WhatsApp / Email", required: false,
                    desc: "Welcome emails, leave decisions and salary slip alerts." },
};

/**
 * ConsentGate — blocks the app on first login until the employee accepts /
 * declines each consent item. Also provides the in-app Privacy & Data screen
 * (export, withdraw, erasure) when accessed via Settings → Privacy.
 */
export default function ConsentGate({ children }) {
  const [state, setState] = useState(null);
  const [showNotice, setShowNotice] = useState(false);

  const load = async () => {
    try { setState((await api.get("/me/privacy")).data); } catch { setState({ needs_initial_consent: false }); }
  };
  useEffect(() => { load(); }, []);

  if (state == null) return <Spinner />;
  if (!state.needs_initial_consent) return children;

  return (
    <ConsentForm
      initial={state.consents}
      onDone={() => load()}
      showNotice={() => setShowNotice(true)}
      noticeOpen={showNotice}
      closeNotice={() => setShowNotice(false)}
    />
  );
}

function ConsentForm({ initial, onDone, showNotice, noticeOpen, closeNotice }) {
  const [vals, setVals] = useState(() => ({
    data_processing: initial?.data_processing ?? false,
    face_capture: initial?.face_capture ?? false,
    geo_location: initial?.geo_location ?? false,
    whatsapp_email: initial?.whatsapp_email ?? true,
  }));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setBusy(true); setErr("");
    try {
      await api.put("/me/privacy/consents", { consents: vals });
      onDone();
    } catch (e) { setErr(fmtErr(e)); } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-5 py-8 bg-gray-50 fade-in">
      <PrivacyNotice open={noticeOpen} onClose={closeNotice} />
      <Card className="max-w-lg w-full">
        <h2 className="font-serif text-2xl text-ink tracking-tight">Your privacy preferences</h2>
        <p className="text-sm text-gray-600 mt-1.5">
          We need your explicit consent before processing your data — this is required by India's <b>Digital Personal Data Protection Act, 2023</b>.
          Read the <button onClick={showNotice} className="text-blue-600 underline" data-testid="open-privacy-notice">full privacy notice</button>.
        </p>
        <div className="mt-5 space-y-3">
          {Object.entries(LABELS).map(([key, def]) => (
            <label key={key} className="flex items-start gap-3 p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50">
              <input
                type="checkbox"
                checked={!!vals[key]}
                onChange={(e) => setVals({ ...vals, [key]: e.target.checked })}
                className="mt-1.5 h-5 w-5 accent-[#2563EB]"
                data-testid={`consent-${key}`}
              />
              <span className="flex-1">
                <span className="font-medium text-ink">{def.name} {def.required && <Badge tone="red">Required</Badge>}</span>
                <span className="block text-xs text-gray-500 mt-0.5">{def.desc}</span>
              </span>
            </label>
          ))}
        </div>
        <p className="text-xs text-gray-500 mt-4">
          You can withdraw any optional consent later in <b>Settings → Privacy</b>. Withdrawing required consent means deleting your account.
        </p>
        {err && <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2 mt-3">{err}</div>}
        <div className="mt-5 flex justify-end">
          <Button onClick={submit} disabled={busy || !vals.data_processing} data-testid="consent-submit">
            {busy ? "Saving…" : "Continue"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
