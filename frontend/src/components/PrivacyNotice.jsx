import React from "react";
import { Modal, Button } from "./ui/Primitives";

/**
 * Privacy notice — fill in {COMPANY_NAME} and {COMPANY_ADDRESS} before going
 * live. This is a template; please have your DPO / legal counsel review.
 */
export default function PrivacyNotice({ open, onClose }) {
  return (
    <Modal open={open} onClose={onClose} title="Privacy Notice"
      footer={<Button onClick={onClose}>Close</Button>}>
      <div className="prose prose-sm max-w-none text-gray-700 space-y-3">
        <p>
          <b>Last updated:</b> May 2026. This notice explains how Payroll &amp; Attendance ("we", "our") processes personal data under
          the <b>Digital Personal Data Protection Act, 2023 (DPDP)</b>.
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
        <p>To run attendance, leave and payroll workflows for your employer. We do not sell your data, do not use it for advertising, and do not share it with third parties except processors (Resend for email, Twilio for WhatsApp, MongoDB Atlas for storage).</p>
        <h4 className="font-semibold text-ink">3. Your rights (DPDP §11–§13)</h4>
        <ul className="list-disc pl-5 space-y-1">
          <li><b>Access</b> — download a JSON bundle of your data anytime.</li>
          <li><b>Correction</b> — request your employer to correct any field.</li>
          <li><b>Erasure</b> — request account deletion. We schedule a 30-day notice and then hard-delete.</li>
          <li><b>Withdraw consent</b> — turn off face capture, GPS or notifications anytime; the app gracefully falls back.</li>
          <li><b>Grievance</b> — write to the Data Protection Officer at <i>(your DPO email)</i>.</li>
        </ul>
        <h4 className="font-semibold text-ink">4. Retention</h4>
        <p>Attendance and leave records are kept for 8 years (Income-Tax Act §44AA). After that they are auto-purged. Salary slips are retained for the same period.</p>
        <h4 className="font-semibold text-ink">5. Data Fiduciary</h4>
        <p><i>(Fill in your registered company name + address before going live.)</i></p>
      </div>
    </Modal>
  );
}
