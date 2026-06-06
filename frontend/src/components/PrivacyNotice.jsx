/* eslint-disable react/no-unescaped-entities */
import React from "react";
import { Modal, Button } from "./ui/Primitives";
import { PRIVACY as P } from "../lib/privacy";

export default function PrivacyNotice({ open, onClose }) {
  return (
    <Modal open={open} onClose={onClose} title="Privacy Notice"
      footer={<Button onClick={onClose}>Close</Button>}>
      <div className="prose prose-sm max-w-none text-gray-700 space-y-3">
        <p>
          <b>Last updated:</b> {P.EFFECTIVE_DATE}. This notice explains how <b>{P.COMPANY_LEGAL_NAME}</b> ("we") processes personal data
          under the <b>Digital Personal Data Protection Act, 2023 (DPDP)</b>.
        </p>
        <h4 className="font-semibold text-ink">1. Data we collect</h4>
        <ul className="list-disc pl-5 space-y-1">
          <li><b>Identity</b> — name, email, employee code, designation, department.</li>
          <li><b>Contact</b> — phone (used for WhatsApp notifications, when you opt in).</li>
          <li><b>Bank</b> — account number and IFSC, for salary disbursement.</li>
          <li><b>Attendance</b> — check-in / check-out time, GPS coordinates (when you opt in), face image hash (never the raw image).</li>
          <li><b>Leave &amp; Salary</b> — leave applications, salary slips for record keeping.</li>
        </ul>
        <h4 className="font-semibold text-ink">2. Purpose</h4>
        <p>To run attendance, leave and payroll workflows for your employer. We do not sell your data, do not use it for advertising, and do not share it with third parties except processors (Resend for email, Twilio for WhatsApp, MongoDB Atlas for storage in {P.ATLAS_REGION}).</p>
        <h4 className="font-semibold text-ink">3. Your rights (DPDP §11–§13)</h4>
        <ul className="list-disc pl-5 space-y-1">
          <li><b>Access</b> — download a JSON bundle of your data anytime.</li>
          <li><b>Correction</b> — request your employer to correct any field.</li>
          <li><b>Erasure</b> — request account deletion. We schedule a 30-day notice and then hard-delete.</li>
          <li><b>Withdraw consent</b> — turn off face capture, GPS or notifications anytime; the app gracefully falls back.</li>
          <li><b>Grievance</b> — write to the Data Protection Officer at <a href={`mailto:${P.DPO_EMAIL}`} className="text-blue-600 underline">{P.DPO_EMAIL}</a>.</li>
        </ul>
        <h4 className="font-semibold text-ink">4. Retention</h4>
        <p>Attendance and leave records are kept for 8 years (Income-Tax Act §44AA). After that they are auto-purged. Salary slips are retained for the same period.</p>
        <h4 className="font-semibold text-ink">5. Data Fiduciary</h4>
        <address className="not-italic">
          <b>{P.COMPANY_LEGAL_NAME}</b><br />
          {P.COMPANY_ADDRESS}<br />
          DPO: {P.DPO_NAME} — <a href={`mailto:${P.DPO_EMAIL}`} className="text-blue-600 underline">{P.DPO_EMAIL}</a><br />
          Grievance: <a href={`mailto:${P.GRIEVANCE_EMAIL}`} className="text-blue-600 underline">{P.GRIEVANCE_EMAIL}</a>
        </address>
      </div>
    </Modal>
  );
}
