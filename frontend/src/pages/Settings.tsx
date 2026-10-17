import { useState } from "react";
import { Button, DataList, Field, FormError, Input, PageHeader, Panel, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useMutation } from "../lib/data";
import { roleName } from "../lib/format";
import { LanguageSelect } from "../lib/i18n";

export default function Settings() {
  const { user, refresh } = useAuth();
  const toast = useToast();
  const [p, setP] = useState({ full_name: user?.full_name ?? "", phone: user?.phone ?? "" });
  const [pw, setPw] = useState({ current_password: "", new_password: "", confirm: "" });
  const save = useMutation(() => api("/auth/me", { method: "PATCH", body: { full_name: p.full_name, phone: p.phone || null } }));
  const change = useMutation(async () => {
    await api("/auth/password", { body: { current_password: pw.current_password, new_password: pw.new_password } });
    return true;
  });
  const perrs = save.error?.fieldErrors() ?? {};
  const cerrs = change.error?.fieldErrors() ?? {};
  if (!user) return null;
  const mismatch = pw.confirm.length > 0 && pw.confirm !== pw.new_password;
  return (
    <>
      <PageHeader title="Account settings" />\n      <Panel title="Regional language"><p className="mb-3 text-sm text-muted">Choose your preferred interface language. Your selection is saved on this device.</p><LanguageSelect /></Panel>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Profile">
          <div className="space-y-4">
            <DataList items={[["Email", user.email], ["Role", roleName(user.role)], ["Organisation", user.organization_name ?? "—"]]} />
            <Field label="Full name" htmlFor="sn" error={perrs.full_name}><Input id="sn" value={p.full_name} onChange={(e) => setP({ ...p, full_name: e.target.value })} /></Field>
            <Field label="Phone" htmlFor="sp" optional><Input id="sp" value={p.phone} onChange={(e) => setP({ ...p, phone: e.target.value })} /></Field>
            <FormError error={save.error} />
            <Button loading={save.pending} onClick={async () => { if (await save.run(undefined)) { await refresh(); toast("Profile saved"); } }}>Save profile</Button>
          </div>
        </Panel>
        <Panel title="Password">
          <div className="space-y-4">
            <Field label="Current password" htmlFor="pc"><Input id="pc" type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field>
            <Field label="New password" htmlFor="pn" hint="At least 10 characters." error={cerrs.new_password}><Input id="pn" type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field>
            <Field label="Repeat new password" htmlFor="pr" error={mismatch ? "Passwords don't match." : undefined}><Input id="pr" type="password" autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} /></Field>
            <FormError error={change.error} />
            <Button loading={change.pending} disabled={!pw.current_password || pw.new_password.length < 10 || mismatch || !pw.confirm} onClick={async () => { if (await change.run(undefined)) { setPw({ current_password: "", new_password: "", confirm: "" }); toast("Password changed"); } }}>Change password</Button>
          </div>
        </Panel>
      </div>
    </>
  );
}
