import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Select, Table } from "../../components/ds";

interface Llp {
  id: string;
  llpin: string;
  name: string;
  registered_address: string | null;
  total_contribution: number | null;
}
interface Partner {
  id: string;
  name: string;
  dpin: string | null;
  is_designated: boolean;
  contribution: number | null;
  profit_share_percent: number | null;
  cessation_date: string | null;
}
interface WorkingPaper {
  fy: number;
  form: string;
  status: string;
  srn: string | null;
  payload: Record<string, string>;
  required_fields: string[];
  optional_fields: string[];
  partner_count: number;
  designated_partner_count: number;
}

function currentFy(): number {
  const now = new Date();
  return now.getFullYear() + (now.getMonth() >= 3 ? 1 : 0);
}

export function LlpsPage() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [openLlp, setOpenLlp] = useState<Llp | null>(null);
  const llps = useQuery({ queryKey: ["llps"], queryFn: () => api.get<Llp[]>("/llps") });
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/llps", body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["llps"] });
    },
    onError: setError,
  });

  return (
    <div className="space-y-4">
      <Card title={`LLPs (${llps.data?.length ?? 0})`}>
        <ErrorText error={error} />
        <form
          className="mb-3 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            create.mutate({
              llpin: f.get("llpin"),
              name: f.get("name"),
              registered_address: (f.get("registered_address") as string) || null,
              total_contribution: Number(f.get("total_contribution")) || null,
            });
            e.currentTarget.reset();
          }}
        >
          <Field label="LLPIN">
            <Input name="llpin" required minLength={7} maxLength={10} />
          </Field>
          <Field label="Name">
            <Input name="name" required />
          </Field>
          <Field label="Registered address">
            <Input name="registered_address" />
          </Field>
          <Field label="Total contribution (₹)">
            <Input name="total_contribution" type="number" />
          </Field>
          <Button type="submit">Add LLP</Button>
        </form>
        {llps.data?.length === 0 ? (
          <Empty>No LLPs yet.</Empty>
        ) : (
          <Table headers={["Name", "LLPIN", "Contribution", ""]}>
            {(llps.data ?? []).map((l) => (
              <tr key={l.id}>
                <td className="px-2 py-2 font-medium">{l.name}</td>
                <td className="px-2 py-2 font-mono text-xs">{l.llpin}</td>
                <td className="px-2 py-2">{l.total_contribution?.toLocaleString() ?? "—"}</td>
                <td className="px-2 py-2 text-right">
                  <button
                    className="text-sm text-indigo-600 hover:underline"
                    onClick={() => setOpenLlp(openLlp?.id === l.id ? null : l)}
                  >
                    {openLlp?.id === l.id ? "Close" : "Open →"}
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      {openLlp && <Partners llp={openLlp} />}
      {openLlp && <WorkingPapers llp={openLlp} />}
    </div>
  );
}

function Partners(props: { llp: Llp }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const partners = useQuery({
    queryKey: ["llp-partners", props.llp.id],
    queryFn: () => api.get<Partner[]>(`/llps/${props.llp.id}/partners`),
  });
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post(`/llps/${props.llp.id}/partners`, body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["llp-partners", props.llp.id] });
    },
    onError: setError,
  });

  return (
    <Card title={`Partners — ${props.llp.name}`}>
      <ErrorText error={error} />
      <form
        className="mb-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          add.mutate({
            name: f.get("name"),
            dpin: (f.get("dpin") as string) || null,
            is_designated: f.get("is_designated") === "on",
            contribution: Number(f.get("contribution")) || null,
            profit_share_percent: Number(f.get("profit_share_percent")) || null,
          });
          e.currentTarget.reset();
        }}
      >
        <Field label="Name">
          <Input name="name" required />
        </Field>
        <Field label="DPIN">
          <Input name="dpin" minLength={8} maxLength={8} />
        </Field>
        <Field label="Contribution (₹)">
          <Input name="contribution" type="number" />
        </Field>
        <Field label="Profit share %">
          <Input name="profit_share_percent" type="number" />
        </Field>
        <label className="flex items-center gap-2 pb-1.5 text-sm">
          <input type="checkbox" name="is_designated" /> Designated
        </label>
        <Button type="submit">Add partner</Button>
      </form>
      <Table headers={["Name", "DPIN", "Role", "Contribution", "Share %"]}>
        {(partners.data ?? []).map((p) => (
          <tr key={p.id}>
            <td className="px-2 py-2">{p.name}</td>
            <td className="px-2 py-2 font-mono text-xs">{p.dpin ?? "—"}</td>
            <td className="px-2 py-2">
              {p.cessation_date ? (
                <Badge>ceased</Badge>
              ) : p.is_designated ? (
                <Badge tone="info">designated</Badge>
              ) : (
                <Badge tone="muted">partner</Badge>
              )}
            </td>
            <td className="px-2 py-2">{p.contribution?.toLocaleString() ?? "—"}</td>
            <td className="px-2 py-2">{p.profit_share_percent ?? "—"}</td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function WorkingPapers(props: { llp: Llp }) {
  const queryClient = useQueryClient();
  const [fy, setFy] = useState(currentFy());
  const [form, setForm] = useState("form11");
  const [error, setError] = useState<unknown>(null);
  const paper = useQuery({
    queryKey: ["llp-wp", props.llp.id, fy, form],
    queryFn: () =>
      api.get<WorkingPaper>(`/llps/${props.llp.id}/working-papers/${fy}/${form}`),
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.put(`/llps/${props.llp.id}/working-papers/${fy}/${form}`, body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["llp-wp", props.llp.id, fy, form] });
    },
    onError: setError,
  });

  const p = paper.data;
  const finalized = p?.status === "finalized";

  return (
    <Card title={`Working papers — ${props.llp.name}`}>
      <div className="mb-3 flex gap-3">
        <Field label="FY (ending year)">
          <Input value={String(fy)} type="number" onChange={(v) => setFy(Number(v))} />
        </Field>
        <Field label="Form">
          <Select
            value={form}
            onChange={setForm}
            options={[
              { value: "form11", label: "Form 11 — Annual Return" },
              { value: "form8", label: "Form 8 — Statement of Account & Solvency" },
            ]}
          />
        </Field>
      </div>
      <ErrorText error={error} />
      {p && (
        <>
          <p className="mb-2 text-xs text-slate-500">
            Active partners: {p.partner_count} (designated: {p.designated_partner_count}) —
            derived from the partners master. Status:{" "}
            <Badge tone={finalized ? "ok" : "muted"}>{p.status}</Badge>
            {p.srn && <> · SRN {p.srn}</>}
          </p>
          <form
            className="grid grid-cols-3 gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              const payload: Record<string, string> = {};
              for (const field of [...p.required_fields, ...p.optional_fields]) {
                const value = (f.get(field) as string).trim();
                if (value) payload[field] = value;
              }
              const finalize = f.get("finalize") === "on";
              save.mutate({
                payload,
                status: finalize ? "finalized" : "draft",
                srn: (f.get("srn") as string) || null,
              });
            }}
          >
            {[...p.required_fields, ...p.optional_fields].map((field) => (
              <Field
                key={field}
                label={`${field.replaceAll("_", " ")}${p.required_fields.includes(field) ? " *" : ""}`}
              >
                <Input name={field} defaultValue={p.payload[field] ?? ""} />
              </Field>
            ))}
            <Field label="SRN (required to finalise)">
              <Input name="srn" defaultValue={p.srn ?? ""} />
            </Field>
            <label className="flex items-center gap-2 pt-5 text-sm">
              <input type="checkbox" name="finalize" /> Finalise (read-only afterwards)
            </label>
            <div className="col-span-3">
              <Button type="submit" disabled={finalized}>
                {finalized ? "Finalised — read-only" : "Save working paper"}
              </Button>
            </div>
          </form>
        </>
      )}
      <p className="mt-2 text-xs text-slate-500">
        Filing deadlines for Form 11/8 come from the compliance rules dataset — this working
        paper assembles the data; filing on MCA remains a manual step by design.
      </p>
    </Card>
  );
}
