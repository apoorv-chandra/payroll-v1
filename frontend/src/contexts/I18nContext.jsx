// i18n — minimal English + Hindi dictionary, no third-party dependency.
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

const DICTS = {
  en: {
    common: {
      sign_in: "Sign in", signing_in: "Signing in…", logout: "Sign out",
      cancel: "Cancel", save: "Save", save_changes: "Save changes",
      saving: "Saving…", delete: "Delete", edit: "Edit",
      add: "Add", confirm: "Confirm", back: "Back", open: "Open",
      yes: "Yes", no: "No", search: "Search", loading: "Loading…",
      next: "Next", prev: "Previous", of: "of", today: "Today",
      pending: "Pending", approved: "Approved", rejected: "Rejected",
      draft: "Draft", disbursed: "Disbursed", active: "Active", inactive: "Inactive",
      yes_delete: "Yes, delete", type_to_confirm: "Type {text} to confirm",
      reauth_password: "Re-enter your password to confirm",
      something_wrong: "Something went wrong. Please try again.",
      none: "—", optional: "Optional",
    },
    nav: {
      overview: "Overview", employers: "Employers", audit: "Audit",
      employees: "Employees", leaves: "Leaves", payroll: "Payroll",
      settings: "Settings", home: "Home", history: "History", salary: "Salary",
      summary: "Summary",
    },
    login: {
      title: "Welcome back",
      sub: "Sign in to manage attendance, leaves & payroll.",
      email: "Email", password: "Password",
      captcha_q: "Solve to continue",
      captcha_refresh: "Refresh",
      demo_creds: "Demo credentials",
      super_admin: "Super Admin",
    },
    employee: {
      not_marked: "Not marked yet",
      day_completed: "Day completed",
      checked_in: "Checked in",
      check_in: "Check in",
      check_out: "Check out",
      mark_for_date: "Mark attendance for date",
      backdate_hint: "You can mark attendance for today or up to {n} days back.",
      replace_existing: "A record already exists for {d}. Replace it?",
      payroll_locked: "Payroll for this month is approved — ask your employer to delete the run first.",
      leave_balances: "Leave balances",
      apply: "Apply",
      from: "From", to: "To",
      leave_type: "Leave type",
      half_day: "Half day",
      reason: "Reason", reason_optional: "Reason (optional)",
      submit: "Submit application",
      no_records: "No records yet",
      verified: "Verified",
      camera_unavailable: "Camera unavailable — tap-only mode",
      blink_once: "Blink once to verify",
      position_face: "Position your face in the frame",
      move_closer: "Move closer & center your face",
    },
    employer: {
      pending_leaves: "Pending leave requests",
      todays_attendance: "Today's attendance",
      employees: "Employees",
      add_employee: "Add employee",
      generate_run: "Generate run",
      delete_run: "Delete payroll run",
      delete_run_warn: "Deleting an approved run unlocks the month for attendance edits and re-payroll. Confirm?",
      submit_for_approval: "Submit for approval",
      approve: "Approve", reject: "Reject",
      pay_cash: "Cash", pay_online: "Online",
      net: "Net",
    },
    accountant: {
      title: "Payroll runs",
      summary_title: "Salary summary",
      list_view: "List", card_view: "Cards",
      total: "Total",
      employee: "Employee",
      net_salary: "Net salary",
      run_status: "Status",
      view_summary: "Open summary",
      submitted: "Submitted for approval",
      edit_deductions: "Edit deductions",
      deduction: "Deduction",
      deduction_note: "Note",
    },
    admin: {
      platform_overview: "Platform overview",
      tenants: "Employers", employees: "Employees",
      attended_today: "Attended today",
      open_payrolls: "Open payrolls",
      add_employer: "Add employer",
      whatsapp_enabled: "WhatsApp notifications enabled",
      max_backdate: "Maximum backdate (days)",
      platform_settings: "Platform settings",
    },
    settings: {
      attendance: "Attendance",
      default_config: "Default config",
      working_days: "Working days / month",
      geofence: "Geo-fence",
      enable_geofence: "Enable geo-fence",
      leave_types: "Leave types",
      reset_month: "Reset month",
    },
  },
  hi: {
    common: {
      sign_in: "साइन इन करें", signing_in: "साइन इन हो रहा है…", logout: "साइन आउट",
      cancel: "रद्द करें", save: "सेव", save_changes: "बदलाव सेव करें",
      saving: "सेव हो रहा है…", delete: "डिलीट", edit: "एडिट",
      add: "जोड़ें", confirm: "पुष्टि करें", back: "वापस", open: "खोलें",
      yes: "हाँ", no: "नहीं", search: "खोजें", loading: "लोड हो रहा है…",
      next: "अगला", prev: "पिछला", of: "में से", today: "आज",
      pending: "लंबित", approved: "स्वीकृत", rejected: "अस्वीकृत",
      draft: "ड्राफ्ट", disbursed: "वितरित", active: "सक्रिय", inactive: "निष्क्रिय",
      yes_delete: "हाँ, डिलीट करें", type_to_confirm: "पुष्टि के लिए {text} टाइप करें",
      reauth_password: "पुष्टि के लिए अपना पासवर्ड फिर से डालें",
      something_wrong: "कुछ गड़बड़ी हुई। कृपया फिर कोशिश करें।",
      none: "—", optional: "वैकल्पिक",
    },
    nav: {
      overview: "अवलोकन", employers: "नियोक्ता", audit: "ऑडिट",
      employees: "कर्मचारी", leaves: "अवकाश", payroll: "वेतन",
      settings: "सेटिंग्स", home: "होम", history: "इतिहास", salary: "सैलरी",
      summary: "सारांश",
    },
    login: {
      title: "वापस स्वागत है",
      sub: "हाजिरी, छुट्टी और वेतन प्रबंधन के लिए साइन इन करें।",
      email: "ईमेल", password: "पासवर्ड",
      captcha_q: "जारी रखने के लिए हल करें",
      captcha_refresh: "रिफ्रेश",
      demo_creds: "डेमो क्रेडेंशियल",
      super_admin: "सुपर एडमिन",
    },
    employee: {
      not_marked: "अभी मार्क नहीं किया",
      day_completed: "दिन पूरा हुआ",
      checked_in: "चेक-इन हो गया",
      check_in: "चेक-इन",
      check_out: "चेक-आउट",
      mark_for_date: "इस तारीख के लिए हाजिरी मार्क करें",
      backdate_hint: "आप आज की या पिछले {n} दिनों तक की हाजिरी मार्क कर सकते हैं।",
      replace_existing: "{d} के लिए पहले से रिकॉर्ड मौजूद है। बदलें?",
      payroll_locked: "इस माह का वेतन स्वीकृत हो चुका है — पहले नियोक्ता से रन हटवाएँ।",
      leave_balances: "छुट्टी का शेष",
      apply: "आवेदन करें",
      from: "से", to: "तक",
      leave_type: "छुट्टी का प्रकार",
      half_day: "आधा दिन",
      reason: "कारण", reason_optional: "कारण (वैकल्पिक)",
      submit: "आवेदन सबमिट करें",
      no_records: "अभी कोई रिकॉर्ड नहीं",
      verified: "सत्यापित",
      camera_unavailable: "कैमरा उपलब्ध नहीं — सिर्फ़ टैप मोड",
      blink_once: "सत्यापन के लिए एक बार पलक झपकाएँ",
      position_face: "अपना चेहरा फ्रेम में रखें",
      move_closer: "थोड़ा पास आएँ और चेहरा बीच में करें",
    },
    employer: {
      pending_leaves: "लंबित अवकाश अनुरोध",
      todays_attendance: "आज की हाजिरी",
      employees: "कर्मचारी",
      add_employee: "कर्मचारी जोड़ें",
      generate_run: "रन जनरेट करें",
      delete_run: "वेतन रन डिलीट करें",
      delete_run_warn: "स्वीकृत रन डिलीट करने पर माह फिर से एडिट योग्य हो जाएगा। पुष्टि करें?",
      submit_for_approval: "स्वीकृति के लिए सबमिट",
      approve: "स्वीकृत", reject: "अस्वीकृत",
      pay_cash: "नकद", pay_online: "ऑनलाइन",
      net: "नेट",
    },
    accountant: {
      title: "वेतन रन",
      summary_title: "वेतन सारांश",
      list_view: "सूची", card_view: "कार्ड",
      total: "कुल",
      employee: "कर्मचारी",
      net_salary: "नेट सैलरी",
      run_status: "स्थिति",
      view_summary: "सारांश खोलें",
      submitted: "स्वीकृति के लिए भेजा गया",
      edit_deductions: "कटौती एडिट करें",
      deduction: "कटौती",
      deduction_note: "नोट",
    },
    admin: {
      platform_overview: "प्लेटफ़ॉर्म अवलोकन",
      tenants: "नियोक्ता", employees: "कर्मचारी",
      attended_today: "आज उपस्थित",
      open_payrolls: "खुले वेतन रन",
      add_employer: "नियोक्ता जोड़ें",
      whatsapp_enabled: "व्हाट्सऐप सूचनाएँ चालू",
      max_backdate: "अधिकतम बैकडेट (दिन)",
      platform_settings: "प्लेटफ़ॉर्म सेटिंग्स",
    },
    settings: {
      attendance: "हाजिरी",
      default_config: "डिफ़ॉल्ट कॉन्फ़िग",
      working_days: "कामकाजी दिन / माह",
      geofence: "जियो-फ़ेंस",
      enable_geofence: "जियो-फ़ेंस चालू करें",
      leave_types: "छुट्टी के प्रकार",
      reset_month: "रीसेट माह",
    },
  },
};

const Ctx = createContext({ lang: "en", t: (k) => k, setLang: () => {} });

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(() => localStorage.getItem("lang") || "en");
  useEffect(() => { localStorage.setItem("lang", lang); document.documentElement.lang = lang; }, [lang]);

  const t = useMemo(() => {
    const dict = DICTS[lang] || DICTS.en;
    return (path, vars) => {
      const parts = path.split(".");
      let cur = dict;
      for (const p of parts) cur = cur?.[p];
      let s = (cur ?? path);
      if (typeof s !== "string") return path;
      if (vars) Object.entries(vars).forEach(([k, v]) => { s = s.replace(`{${k}}`, v); });
      return s;
    };
  }, [lang]);

  const setLang = (l) => setLangState(l === "hi" ? "hi" : "en");

  return <Ctx.Provider value={{ lang, t, setLang }}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);
