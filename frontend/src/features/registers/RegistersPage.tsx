import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Table } from "../../components/ds";
import { useSession } from "../../app/session";

interface RegisterSummary {
  type: string;
  name: string;
  section: string;
  mandatory: boolean;
  required_fields: string[];
  optional_fields: string[];
  entries: number;
}

interface RegisterEntry {
  entry_key: string;
  version: number;
  payload: Record<string, string>;
  is_deleted: boolean;
  delete_reason: string | null;
  recorded_at: string;
}

export function RegistersPage() {
  const session = useSession();
  const [open, setOpen] = useState<RegisterSummary | null>(null);
  const company = session.workingCompany;

  const summary = useQuery({
    enabled: !!company,
    queryKey: ["registers", company?.id],
    queryFn: () => api.get<RegisterSummary[]>(`/companies/${company!.id}/registers`),
  });

  if (!company) {
    return <Empty>Select a working company in the sidebar to maintain its registers.</Empty>;
  }

  return (
    <div className="space-y-4">
      <Card title={`Statutory registers — ${company.name} (append-only: every change is a new version, history is permanent)`}>
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
          {(summary.data ?? []).map((r) => (
            <button
              key={r.type}
              onClick={() => setOpen(r)}
              className={`rounded-md border p-3 text-left text-sm hover:border-indigo-400 ${
                open?.type === r.type ? "border-indigo-500 bg-indigo-50" : "border-slate-200"
              }`}
            >
              <p className="font-medium">{r.name}</p>
              <p className="text-xs text-slate-500">
                {r.section} · {r.mandatory ? "mandatory" : "optional"} ·{" "}
                {r.entries} entr{r.entries === 1 ? "y" : "ies"}
              </p>
            </button>
          ))}
        </div>
      </Card>
      {open && <RegisterDetail companyId={company.id} register={open} />}
    </div>
  );
}

function RegisterDetail(props: { companyId: string; register: RegisterSummary }) {
  const { companyId, register } = props;
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [amending, setAmending] = useState<RegisterEntry | null>(null);
  const [historyKey, setHistoryKey] = useState<string | null>(null);

  const entries = useQuery({
    queryKey: ["register-entries", companyId, register.type],
    queryFn: () =>
      api.get<RegisterEntry[]>(`/companies/${companyId}/registers/${register.type}`),
  });
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["register-entries", companyId, register.type] });
    void queryClient.invalidateQueries({ queryKey: ["registers", companyId] });
  };
  const create = useMutation({
    mutationFn: (payload: Record<string, string>) =>
      api.post(`/companies/${companyId}/registers/${register.type}`, { payload }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: setError,
  });
  const amend = useMutation({
    mutationFn: ({ entry, payload }: { entry: RegisterEntry; payload: Record<string, string> }) =>
      api.put(`/register-entries/${entry.entry_key}`, {
        payload,
        expected_version: entry.version,
      }),
    onSuccess: () => {
      setAmending(null);
      setError(null);
      invalidate();
    },
    onError: setError,
  });
  const remove = useMutation({
    mutationFn: ({ key, reason }: { key: string; reason: string }) =>
      api.del(`/register-entries/${key}`, { reason }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: setError,
  });

  const fields = [...register.required_fields, ...register.optional_fields];

  return (
    <Card
      title={`${register.name} (${register.section})`}
      actions={
        <a
          className="text-sm text-indigo-600 hover:underline"
          href={`/api/v1/companies/${companyId}/registers/${register.type}/export`}
        >
          Export (as-on stamped)
        </a>
      }
    >
      <ErrorText error={error} />
      <EntryForm
        key={amending?.entry_key ?? "new"}
        fields={fields}
        required={register.required_fields}
        initial={amending?.payload}
        submitLabel={amending ? `Save as version ${amending.version + 1}` : "Add entry"}
        onCancel={amending ? () => setAmending(null) : undefined}
        onSubmit={(payload) =>
          amending ? amend.mutate({ entry: amending, payload }) : create.mutate(payload)
        }
      />
      {entries.data?.length === 0 ? (
        <Empty>No entries in this register yet.</Empty>
      ) : (
        <Table headers={[...fields.slice(0, 5), "version", ""]}>
          {(entries.data ?? []).map((e) => (
            <tr key={e.entry_key}>
              {fields.slice(0, 5).map((f) => (
                <td key={f} className="px-2 py-2 text-xs">
                  {e.payload[f] ?? "—"}
                </td>
              ))}
              <td className="px-2 py-2">
                <Badge tone="info">v{e.version}</Badge>
              </td>
              <td className="space-x-2 px-2 py-2 text-right text-sm whitespace-nowrap">
                <button className="text-indigo-600 hover:underline" onClick={() => setAmending(e)}>
                  Amend
                </button>
                <button
                  className="text-slate-500 hover:underline"
                  onClick={() => setHistoryKey(historyKey === e.entry_key ? null : e.entry_key)}
                >
                  History
                </button>
                <button
                  className="text-rose-600 hover:underline"
                  onClick={() => {
                    const reason = window.prompt(
                      "Delete entry (Partner only; stays in history) — reason:",
                    );
                    if (reason) remove.mutate({ key: e.entry_key, reason });
                  }}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </Table>
      )}
      {historyKey && <History entryKey={historyKey} fields={fields} />}
    </Card>
  );
}

function EntryForm(props: {
  fields: string[];
  required: string[];
  initial?: Record<string, string>;
  submitLabel: string;
  onCancel?: () => void;
  onSubmit: (payload: Record<string, string>) => void;
}) {
  return (
    <form
      className="mb-4 grid grid-cols-4 gap-2 rounded-md bg-slate-50 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        const payload: Record<string, string> = {};
        for (const field of props.fields) {
          const value = (f.get(field) as string).trim();
          if (value) payload[field] = value;
        }
        props.onSubmit(payload);
        if (!props.initial) e.currentTarget.reset();
      }}
    >
      {props.fields.map((field) => (
        <Field
          key={field}
          label={`${field.replaceAll("_", " ")}${props.required.includes(field) ? " *" : ""}`}
        >
          <Input
            name={field}
            defaultValue={props.initial?.[field] ?? ""}
            required={props.required.includes(field)}
          />
        </Field>
      ))}
      <div className="col-span-4 flex gap-2">
        <Button type="submit">{props.submitLabel}</Button>
        {props.onCancel && (
          <Button variant="ghost" onClick={props.onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

function History(props: { entryKey: string; fields: string[] }) {
  const versions = useQuery({
    queryKey: ["register-history", props.entryKey],
    queryFn: () => api.get<RegisterEntry[]>(`/register-entries/${props.entryKey}/history`),
  });
  return (
    <div className="mt-3 rounded-md border border-slate-200 p-3">
      <h3 className="mb-2 text-sm font-semibold">Full history (immutable)</h3>
      <Table headers={["version", "recorded", "state", ...props.fields.slice(0, 4)]}>
        {(versions.data ?? []).map((v) => (
          <tr key={v.version}>
            <td className="px-2 py-2">v{v.version}</td>
            <td className="px-2 py-2 text-xs">{new Date(v.recorded_at).toLocaleString()}</td>
            <td className="px-2 py-2">
              {v.is_deleted ? (
                <Badge tone="warn">deleted: {v.delete_reason}</Badge>
              ) : (
                <Badge tone="ok">active</Badge>
              )}
            </td>
            {props.fields.slice(0, 4).map((f) => (
              <td key={f} className="px-2 py-2 text-xs">
                {v.payload[f] ?? "—"}
              </td>
            ))}
          </tr>
        ))}
      </Table>
    </div>
  );
}
