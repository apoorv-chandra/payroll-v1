# PRIVACY POLICY — Payroll & Attendance Platform

> ⚠️ **TEMPLATE — fill in everything in `{{CURLY_BRACES}}` and have your DPO / legal counsel review before going live.**

**Effective date:** {{EFFECTIVE_DATE}}
**Last updated:** {{LAST_UPDATED}}

---

## 1. Who we are (Data Fiduciary)

- **Legal name:** {{COMPANY_LEGAL_NAME}}
- **Registered address:** {{COMPANY_ADDRESS}}
- **CIN / Registration #:** {{COMPANY_CIN}}
- **Data Protection Officer:** {{DPO_NAME}} — {{DPO_EMAIL}} — {{DPO_PHONE}}
- **Grievance Officer:** {{GRIEVANCE_OFFICER_EMAIL}}

This notice describes how we collect, process and protect your personal data under the **Digital Personal Data Protection Act, 2023 (DPDP)** and the rules thereunder. By signing in to the Payroll & Attendance app you confirm you have read and understood this notice.

## 2. Data we collect

| Category | Examples | Lawful basis |
|----------|----------|--------------|
| Identity | Name, employee code, designation, department | Performance of contract (employment) |
| Contact | Work email, phone (for WhatsApp / email alerts) | Consent (notifications) |
| Financial | Bank A/C, IFSC, monthly salary, salary slips | Legal obligation (Payment of Wages Act) |
| Attendance | Check-in / check-out timestamps, GPS coords (optional), face image **hash** (not the raw image) | Consent + legitimate interest (work-time tracking) |
| Leave | Leave applications, balances, approvals | Performance of contract |

**We never collect raw photos, voice prints, biometrics or government IDs.** Face captures are immediately reduced to an anonymous SHA-256 hash before storage.

## 3. Purpose of processing

To run attendance, leave and payroll workflows for {{EMPLOYER_OR_TENANT_REFERENCE}}. We do not sell your data, do not use it for advertising, and do not share it with third parties except processors listed below.

## 4. Processors / sub-processors

| Processor | Purpose | Region |
|-----------|---------|--------|
| MongoDB Atlas | Primary database | {{ATLAS_REGION}} |
| Resend | Transactional email | EU/US |
| Twilio | WhatsApp business messages | US |
| RazorpayX (when enabled) | Salary disbursement | India |

## 5. Your DPDP rights

| Right | How to exercise |
|-------|-----------------|
| **Access (§11)** | Settings → Privacy → "Download my data" |
| **Correction** | Ask your employer's HR/admin |
| **Erasure (§12)** | Settings → Privacy → "Request deletion" — completed in 30 days |
| **Withdraw consent** | Settings → Privacy → toggle off any optional consent |
| **Grievance redressal (§13)** | Email {{GRIEVANCE_OFFICER_EMAIL}}; we respond within 7 days |
| **Nominate** | Email {{DPO_EMAIL}} with your nominee's contact details |

## 6. Retention

| Data | Retention period | Then |
|------|------------------|------|
| Attendance | 8 years (Income-Tax Act §44AA) | Auto-deleted |
| Leave records | 8 years | Auto-deleted |
| Salary slips | 8 years | Auto-deleted |
| Audit log | 1 year | Anonymised |
| Active sessions | 12 hours | Token expires |
| Captcha tokens | 5 minutes | Auto-deleted (TTL index) |

## 7. Security

- TLS 1.2+ on all connections
- bcrypt password hashing (cost 12)
- JWT short-lived access tokens (12 h)
- Passwordless captcha re-entry on critical actions (delete, payroll approval)
- Tenant isolation enforced at the query layer
- Audit log on every write
- (Optional) MongoDB encryption-at-rest via Atlas

## 8. Children's data

We do not knowingly process data of individuals under 18 (DPDP §9). Employers are responsible for verifying age and obtaining parental consent before adding under-18 employees.

## 9. Cross-border transfer

Data is stored in {{ATLAS_REGION}}. Transactional providers (Resend, Twilio) may process metadata in jurisdictions notified under DPDP §16. We do not transfer data to any country restricted by the Government.

## 10. Data Breach

In the event of a personal data breach, we notify the Data Protection Board and affected Data Principals without undue delay, and in any case within **72 hours** of becoming aware.

## 11. Updates

We may update this notice; material changes are communicated via in-app banner and email. The "Last updated" date at the top reflects the latest version.

## 12. Contact

- Grievance / DPO: {{DPO_EMAIL}}
- Postal: {{COMPANY_ADDRESS}}
