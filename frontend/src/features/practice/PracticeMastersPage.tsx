import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Table } from "../../components/ds";

interface AuditorRow {
  id: string;
  firm_name: string;
  frn: string;
  email: string | null;
}
interface PcsRow {
  id: string;
  name: string;
  membership_no: string;
  cop_no: string | null;
  firm_name: string | null;
}
interface DscRow {
  id: string;
  holder_name: string;
  token_color: string | null;
  token_number: string | null;
  expiry_date: string | null;
  remarks: string | null;
}

export function PracticeMastersPage() {
  return (
    <div className="space-y-4">
      <Auditors />
      <Pcs />
      <Dsc />
    </div>
  );
}

function Auditors() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const auditors = useQuery({
    queryKey: ["auditors"],
    queryFn: () => api.get<AuditorRow[]>("/auditors"),
  });
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/auditors", body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["auditors"] });
    },
    onError: setError,
  });

  return (
    <Card title="Auditors (CA firms, reusable across engagements)">
      <ErrorText error={error} />
      <form
        className="mb-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          add.mutate({
            firm_name: f.get("firm_name"),
            frn: f.get("frn"),
            email: (f.get("email") as string) || null,
          });
          e.currentTarget.reset();
        }}
      >
        <Field label="Firm name">
          <Input name="firm_name" required />
        </Field>
        <Field label="FRN">
          <Input name="frn" required />
        </Field>
        <Field label="Email">
          <Input name="email" type="email" />
        </Field>
        <Button type="submit">Add auditor</Button>
      </form>
      {auditors.data?.length === 0 ? (
        <Empty>No auditor firms yet.</Empty>
      ) : (
        <Table headers={["Firm", "FRN", "Email"]}>
          {(auditors.data ?? []).map((a) => (
            <tr key={a.id}>
              <td className="px-2 py-2">{a.firm_name}</td>
              <td className="px-2 py-2 font-mono text-xs">{a.frn}</td>
              <td className="px-2 py-2 text-xs">{a.email ?? "—"}</td>
            </tr>
          ))}
        </Table>
      )}
      <p className="mt-2 text-xs text-slate-500">
        Appointment history per company lives on the company via
        /auditor-appointments (ADT-1 SRN tracked per engagement).
      </p>
    </Card>
  );
}

function Pcs() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const pcs = useQuery({ queryKey: ["pcs"], queryFn: () => api.get<PcsRow[]>("/pcs") });
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/pcs", body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["pcs"] });
    },
    onError: setError,
  });

  return (
    <Card title="PCS master (signing blocks & letterheads)">
      <ErrorText error={error} />
      <form
        className="mb-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          add.mutate({
            name: f.get("name"),
            membership_no: f.get("membership_no"),
            cop_no: (f.get("cop_no") as string) || null,
            firm_name: (f.get("firm_name") as string) || null,
          });
          e.currentTarget.reset();
        }}
      >
        <Field label="Name">
          <Input name="name" required />
        </Field>
        <Field label="Membership no.">
          <Input name="membership_no" required />
        </Field>
        <Field label="COP no.">
          <Input name="cop_no" />
        </Field>
        <Field label="Firm">
          <Input name="firm_name" />
        </Field>
        <Button type="submit">Add PCS</Button>
      </form>
      {pcs.data?.length === 0 ? (
        <Empty>No practicing professionals recorded.</Empty>
      ) : (
        <Table headers={["Name", "Membership", "COP", "Firm"]}>
          {(pcs.data ?? []).map((p) => (
            <tr key={p.id}>
              <td className="px-2 py-2">{p.name}</td>
              <td className="px-2 py-2 font-mono text-xs">{p.membership_no}</td>
              <td className="px-2 py-2 font-mono text-xs">{p.cop_no ?? "—"}</td>
              <td className="px-2 py-2 text-xs">{p.firm_name ?? "—"}</td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

function expiringSoon(expiry: string | null): boolean {
  if (!expiry) return false;
  const days = (new Date(expiry).getTime() - Date.now()) / 86_400_000;
  return days <= 30;
}

function Dsc() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const tokens = useQuery({
    queryKey: ["dsc"],
    queryFn: () => api.get<DscRow[]>("/dsc-tokens"),
  });
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/dsc-tokens", body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["dsc"] });
    },
    onError: setError,
  });

  return (
    <Card title="DSC token tracker">
      <ErrorText error={error} />
      <form
        className="mb-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          add.mutate({
            holder_name: f.get("holder_name"),
            token_color: (f.get("token_color") as string) || null,
            token_number: (f.get("token_number") as string) || null,
            expiry_date: (f.get("expiry_date") as string) || null,
          });
          e.currentTarget.reset();
        }}
      >
        <Field label="Holder">
          <Input name="holder_name" required />
        </Field>
        <Field label="Token colour">
          <Input name="token_color" />
        </Field>
        <Field label="Token no.">
          <Input name="token_number" />
        </Field>
        <Field label="Expiry">
          <Input name="expiry_date" type="date" />
        </Field>
        <Button type="submit">Add token</Button>
      </form>
      {tokens.data?.length === 0 ? (
        <Empty>No DSC tokens tracked.</Empty>
      ) : (
        <Table headers={["Holder", "Token", "Expiry", ""]}>
          {(tokens.data ?? []).map((t) => (
            <tr key={t.id}>
              <td className="px-2 py-2">{t.holder_name}</td>
              <td className="px-2 py-2 text-xs">
                {t.token_color ?? "—"} {t.token_number ? `· ${t.token_number}` : ""}
              </td>
              <td className="px-2 py-2">{t.expiry_date ?? "—"}</td>
              <td className="px-2 py-2">
                {expiringSoon(t.expiry_date) && <Badge tone="warn">expiring soon</Badge>}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
