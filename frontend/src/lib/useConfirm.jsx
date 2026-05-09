/**
 * useConfirm — promise-based confirmation hook.
 *
 * Three styles:
 *   - "simple"  → Yes / No
 *   - "type"    → user must type a phrase to enable the confirm button
 *   - "password"→ user must re-enter their current password
 *
 *   const { confirm, ConfirmHost } = useConfirm();
 *   const ok = await confirm({ kind: "type", title: "Delete Acme Inc?", typeText: "Acme Inc" });
 */
import React, { useCallback, useRef, useState } from "react";
import { Button, Input, Modal } from "../components/ui/Primitives";
import { api } from "./api";

export default function useConfirm() {
  const [state, setState] = useState(null); // { kind, title, body, typeText, danger, resolve }
  const inputRef = useRef(null);
  const [typed, setTyped] = useState("");
  const [pwd, setPwd] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const confirm = useCallback((opts) => new Promise((resolve) => {
    setTyped(""); setPwd(""); setErr(""); setBusy(false);
    setState({ ...opts, resolve });
  }), []);

  const close = (val) => {
    state?.resolve?.(val);
    setState(null);
  };

  const tryConfirm = async () => {
    if (!state) return;
    if (state.kind === "type") {
      if (typed.trim() !== (state.typeText || "")) { setErr("Text doesn't match."); return; }
    }
    if (state.kind === "password") {
      setBusy(true); setErr("");
      try {
        const cap = await api.get("/auth/captcha").then((r) => r.data);
        const me = JSON.parse(localStorage.getItem("auth_user") || "null");
        await api.post("/auth/login", {
          email: me?.email,
          password: pwd,
          captcha_token: cap.token,
          captcha_answer: cap.op === "+" ? cap.a + cap.b : cap.a - cap.b,
        });
      } catch (e) {
        setErr("Password incorrect.");
        setBusy(false);
        return;
      } finally { setBusy(false); }
    }
    close(true);
  };

  const ConfirmHost = (
    <Modal
      open={!!state}
      onClose={() => close(false)}
      title={state?.title || "Are you sure?"}
      footer={state ? (
        <>
          <Button variant="secondary" onClick={() => close(false)} data-testid="confirm-cancel">Cancel</Button>
          <Button
            variant={state.danger ? "danger" : "primary"}
            onClick={tryConfirm}
            disabled={busy || (state.kind === "type" && typed.trim() !== state.typeText) || (state.kind === "password" && !pwd)}
            data-testid="confirm-ok"
          >
            {state.confirmText || (state.danger ? "Yes, continue" : "Confirm")}
          </Button>
        </>
      ) : null}
    >
      {state && (
        <div className="space-y-3">
          {state.body && <p className="text-sm text-gray-700">{state.body}</p>}
          {state.kind === "type" && (
            <Input
              ref={inputRef}
              autoFocus
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              label={`Type "${state.typeText}" to confirm`}
              data-testid="confirm-type-input"
            />
          )}
          {state.kind === "password" && (
            <Input
              type="password"
              autoFocus
              value={pwd}
              onChange={(e) => setPwd(e.target.value)}
              label="Re-enter your password"
              data-testid="confirm-password-input"
            />
          )}
          {err && <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">{err}</div>}
        </div>
      )}
    </Modal>
  );

  return { confirm, ConfirmHost };
}
