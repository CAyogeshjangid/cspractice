import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { Company, Director, Disclosure, ImportReport, Shareholder, Taxonomy } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Table } from "../../components/ds";

type Tab = "directors" | "shareholders" | "fy";

export function CompanyDetail() {
  const { companyId } = useParams();
  const [tab, setTab] = useState<Tab>("directors");
  const company = useQuery({
    queryKey: ["company", companyId],
    queryFn: () => api.get<Company>(`/companies/${companyId}`),
  });

  if (!company.data) return <p className="text-sm text-slate-500">Loading…</p>;
  const c = company.data;

  return (
    <div className="space-y-4">
      <Card title={c.name}>
        <dl className="grid grid-cols-4 gap-3 text-sm">
          <Info label="CIN" value={c.cin} mono />
          <Info label="AGM date" value={c.agm_date ?? "—"} />
          <Info label="FY end" value={`${c.fy_end_day}/${c.fy_end_month}`} />
          <Info label="Paid-up capital" value={c.paidup_capital?.toLocaleString() ?? "—"} />
        </dl>
        <CompanyActions company={c} />
      </Card>
      <div className="flex gap-2">
        {(["directors", "shareholders", "fy"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              tab === t ? "bg-indigo-600 text-white" : "border border-slate-300 text-slate-600"
            }`}
          >
            {t === "fy" ? "FY attributes" : t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      {tab === "directors" && <Directors companyId={c.id} />}
      {tab === "shareholders" && <Shareholders companyId={c.id} />}
      {tab === "fy" && <FyAttributes companyId={c.id} />}
    </div>
  );
}

function CompanyActions(props: { company: Company }) {
  const c = props.company;
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.put(`/companies/${c.id}`, body),
    onSuccess: () => {
      setEditing(false);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["company", c.id] });
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: setError,
  });
  const remove = useMutation({
    mutationFn: (reason: string) => api.del(`/companies/${c.id}`, { reason }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
      navigate("/");
    },
    onError: setError,
  });

  return (
    <div className="mt-3 border-t border-slate-100 pt-3">
      <ErrorText error={error} />
      <div className="flex gap-2">
        <Button variant="ghost" onClick={() => setEditing(!editing)}>
          {editing ? "Close" : "Edit company"}
        </Button>
        <Button
          variant="danger"
          onClick={() => {
            const reason = window.prompt(
              "Soft delete (Partner only, kept in history) — reason:",
            );
            if (reason) remove.mutate(reason);
          }}
        >
          Delete (soft)
        </Button>
      </div>
      {editing && (
        <form
          className="mt-3 grid grid-cols-3 gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            const body: Record<string, unknown> = {};
            const agm = f.get("agm_date") as string;
            if (agm) body.agm_date = agm;
            const addr = f.get("registered_address") as string;
            if (addr) body.registered_address = addr;
            const paidup = f.get("paidup_capital") as string;
            if (paidup) body.paidup_capital = Number(paidup);
            body.is_listed = f.get("is_listed") === "on";
            body.professional_group_id = (f.get("professional_group_id") as string) || null;
            body.industry_id = (f.get("industry_id") as string) || null;
            update.mutate(body);
          }}
        >
          <Field label="AGM date">
            <Input name="agm_date" type="date" defaultValue={c.agm_date ?? ""} />
          </Field>
          <Field label="Registered address">
            <Input name="registered_address" defaultValue={c.registered_address ?? ""} />
          </Field>
          <Field label="Paid-up capital (₹)">
            <Input
              name="paidup_capital"
              type="number"
              defaultValue={c.paidup_capital != null ? String(c.paidup_capital) : ""}
            />
          </Field>
          <TaxonomyPicker
            kind="professional-groups"
            label="Professional group"
            name="professional_group_id"
            current={c.professional_group_id}
          />
          <TaxonomyPicker kind="industries" label="Industry" name="industry_id" current={c.industry_id} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" name="is_listed" defaultChecked={c.is_listed} /> Listed company
          </label>
          <div className="col-span-3">
            <Button type="submit">Save changes</Button>
          </div>
        </form>
      )}
    </div>
  );
}

/** Firm-scoped tag select with inline creation (taxonomies are user-extensible, PRD §3). */
function TaxonomyPicker(props: {
  kind: "professional-groups" | "industries";
  label: string;
  name: string;
  current: string | null;
}) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(props.current ?? "");
  const options = useQuery({
    queryKey: ["taxonomy", props.kind],
    queryFn: () => api.get<Taxonomy[]>(`/taxonomies/${props.kind}`),
  });
  const create = useMutation({
    mutationFn: (name: string) => api.post<Taxonomy>(`/taxonomies/${props.kind}`, { name }),
    onSuccess: (created) => {
      setValue(created.id);
      void queryClient.invalidateQueries({ queryKey: ["taxonomy", props.kind] });
    },
  });

  return (
    <Field label={props.label}>
      <div className="flex gap-1">
        <select
          name={props.name}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm"
        >
          <option value="">— none —</option>
          {(options.data ?? []).map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
          {/* keep a just-created tag selectable before the list refetches */}
          {create.data && !options.data?.some((t) => t.id === create.data.id) && (
            <option value={create.data.id}>{create.data.name}</option>
          )}
        </select>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            const name = window.prompt(`New ${props.label.toLowerCase()} name:`);
            if (name?.trim()) create.mutate(name.trim());
          }}
        >
          +
        </Button>
      </div>
    </Field>
  );
}


function Info(props: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase text-slate-400">{props.label}</dt>
      <dd className={props.mono ? "font-mono text-xs" : ""}>{props.value}</dd>
    </div>
  );
}

/** Excel template / import / export controls for a per-company master
 *  (directors or shareholders) — same contract as the companies list:
 *  all-or-nothing import, row-level 422 report, idempotent skips. */
function useMasterIo(companyId: string, master: "directors" | "shareholders") {
  const queryClient = useQueryClient();
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const base = `/companies/${companyId}/${master}`;

  const importFile = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.upload<ImportReport>(`${base}/import`, form);
    },
    onSuccess: (result) => {
      setReport(result);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: [master, companyId] });
    },
    onError: (err) => {
      // 422 carries the row-level validation report
      const detail = (err as { detail?: ImportReport }).detail;
      setReport(detail && Array.isArray(detail.errors) ? detail : null);
      setError(err);
    },
  });

  const actions = (
    <>
      <a href={`/api/v1${base}/import/template`} className="text-sm text-indigo-600 hover:underline">
        Import template
      </a>
      <a href={`/api/v1${base}/export`} className="text-sm text-indigo-600 hover:underline">
        Export
      </a>
      <label className="cursor-pointer rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
        Import Excel
        <input
          type="file"
          accept=".xlsx"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) importFile.mutate(file);
            e.target.value = "";
          }}
        />
      </label>
    </>
  );

  const reportView = (
    <>
      {error != null && !report && <ErrorText error={error} />}
      {report && (
        <div className="mb-3 rounded-md bg-slate-50 p-3 text-sm">
          {report.errors.length === 0 ? (
            <p className="text-emerald-700">
              Imported: {report.created ?? 0} created, {report.skipped ?? 0} already present
              (skipped).
            </p>
          ) : (
            <>
              <p className="mb-1 font-medium text-rose-700">
                Nothing was imported — fix these rows and re-upload (all-or-nothing):
              </p>
              <ul className="list-inside list-disc text-rose-700">
                {report.errors.slice(0, 20).map((e, i) => (
                  <li key={i}>
                    Row {e.row}, {e.column}: {e.error}
                  </li>
                ))}
                {report.errors.length > 20 && <li>…and {report.errors.length - 20} more</li>}
              </ul>
            </>
          )}
        </div>
      )}
    </>
  );

  return { actions, reportView };
}

// Indian FY ends 31 March; FY is named by its ending year (JS months are 0-indexed)
const currentFy = () => new Date().getFullYear() + (new Date().getMonth() >= 3 ? 1 : 0);

function Directors(props: { companyId: string }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [disclosureFor, setDisclosureFor] = useState<Director | null>(null);
  const directors = useQuery({
    queryKey: ["directors", props.companyId],
    queryFn: () => api.get<Director[]>(`/companies/${props.companyId}/directors`),
  });
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post(`/companies/${props.companyId}/directors`, body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["directors", props.companyId] });
    },
    onError: setError,
  });
  const io = useMasterIo(props.companyId, "directors");

  return (
    <Card title="Directors" actions={io.actions}>
      {io.reportView}
      <ErrorText error={error} />
      <form
        className="mb-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          add.mutate({
            name: f.get("name"),
            din: (f.get("din") as string) || null,
            designation: (f.get("designation") as string) || null,
            din_allocation_date: (f.get("din_allocation_date") as string) || null,
          });
          e.currentTarget.reset();
        }}
      >
        <Field label="Name">
          <Input name="name" required />
        </Field>
        <Field label="DIN (8 digits)">
          <Input name="din" minLength={8} maxLength={8} />
        </Field>
        <Field label="Designation">
          <Input name="designation" />
        </Field>
        <Field label="DIN allocation date">
          <Input name="din_allocation_date" type="date" />
        </Field>
        <Button type="submit">Add</Button>
      </form>
      {directors.data?.length === 0 ? (
        <Empty>No directors recorded.</Empty>
      ) : (
        <Table headers={["Name", "DIN", "Designation", "Active", ""]}>
          {(directors.data ?? []).map((d) => (
            <tr key={d.id}>
              <td className="px-2 py-2">{d.name}</td>
              <td className="px-2 py-2 font-mono text-xs">{d.din ?? "—"}</td>
              <td className="px-2 py-2">{d.designation ?? "—"}</td>
              <td className="px-2 py-2">
                {d.is_active ? <Badge tone="ok">active</Badge> : <Badge>ceased</Badge>}
              </td>
              <td className="px-2 py-2 text-right">
                <button
                  onClick={() => setDisclosureFor(disclosureFor?.id === d.id ? null : d)}
                  className="text-sm text-indigo-600 hover:underline"
                >
                  {disclosureFor?.id === d.id ? "Close disclosures" : "Disclosures"}
                </button>
              </td>
            </tr>
          ))}
        </Table>
      )}
      {disclosureFor && <DisclosurePanel companyId={props.companyId} director={disclosureFor} />}
    </Card>
  );
}

/** Per-FY MBP-1 / DIR-8 / DIR-2 received dates for one director (PRD §4.3). */
function DisclosurePanel(props: { companyId: string; director: Director }) {
  const queryClient = useQueryClient();
  const d = props.director;
  const base = `/companies/${props.companyId}/directors/${d.id}/disclosures`;
  const [fy, setFy] = useState(currentFy());
  const [error, setError] = useState<unknown>(null);
  const disclosures = useQuery({
    queryKey: ["disclosures", d.id],
    queryFn: () => api.get<Disclosure[]>(base),
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.put(`${base}/${fy}`, body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["disclosures", d.id] });
    },
    onError: setError,
  });
  const existing = disclosures.data?.find((r) => r.fy === fy);

  const FIELDS = [
    { name: "mbp1_received", label: "MBP-1 (interest in entities)" },
    { name: "dir8_received", label: "DIR-8 (non-disqualification)" },
    { name: "dir2_received", label: "DIR-2 (consent to act)" },
  ] as const;

  return (
    <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3">
      <p className="mb-2 text-sm font-medium">
        Annual disclosures — {d.name} (dates the firm received each form)
      </p>
      <ErrorText error={error} />
      <form
        // remount when the FY or its stored row changes so defaults refresh
        key={`${d.id}:${fy}:${existing ? existing.fy : "new"}`}
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          save.mutate(
            Object.fromEntries(
              FIELDS.map(({ name }) => [name, (f.get(name) as string) || null]),
            ),
          );
        }}
      >
        <Field label="FY (ending year)">
          <Input value={String(fy)} type="number" onChange={(v) => setFy(Number(v))} />
        </Field>
        {FIELDS.map(({ name, label }) => (
          <Field key={name} label={label}>
            <Input name={name} type="date" defaultValue={existing?.[name] ?? ""} />
          </Field>
        ))}
        <Button type="submit">Save disclosures</Button>
      </form>
      {(disclosures.data ?? []).length > 0 && (
        <div className="mt-3">
          <Table headers={["FY", "MBP-1", "DIR-8", "DIR-2"]}>
            {(disclosures.data ?? []).map((row) => (
              <tr key={row.fy}>
                <td className="px-2 py-2">{row.fy}</td>
                {FIELDS.map(({ name }) => (
                  <td key={name} className="px-2 py-2">
                    {row[name] ? <Badge tone="ok">{row[name]}</Badge> : <Badge>pending</Badge>}
                  </td>
                ))}
              </tr>
            ))}
          </Table>
        </div>
      )}
    </div>
  );
}

function Shareholders(props: { companyId: string }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const holders = useQuery({
    queryKey: ["shareholders", props.companyId],
    queryFn: () =>
      api.get<{
        shareholders: Shareholder[];
        total_shares: string;
        total_percentage: string;
        percentage_warning: boolean;
      }>(`/companies/${props.companyId}/shareholders`),
  });
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post(`/companies/${props.companyId}/shareholders`, body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["shareholders", props.companyId] });
    },
    onError: setError,
  });
  const io = useMasterIo(props.companyId, "shareholders");

  return (
    <Card title="Shareholders (cap table)" actions={io.actions}>
      {io.reportView}
      <ErrorText error={error} />
      {holders.data?.percentage_warning && (
        <p className="mb-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Percentages total {holders.data.total_percentage}% — expected ~100%.
        </p>
      )}
      <form
        className="mb-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          add.mutate({
            name: f.get("name"),
            folio: (f.get("folio") as string) || null,
            shares: Number(f.get("shares")) || null,
            percentage: Number(f.get("percentage")) || null,
          });
          e.currentTarget.reset();
        }}
      >
        <Field label="Name">
          <Input name="name" required />
        </Field>
        <Field label="Folio">
          <Input name="folio" />
        </Field>
        <Field label="Shares">
          <Input name="shares" type="number" />
        </Field>
        <Field label="%">
          <Input name="percentage" type="number" />
        </Field>
        <Button type="submit">Add</Button>
      </form>
      <Table headers={["Name", "Folio", "Shares", "%"]}>
        {(holders.data?.shareholders ?? []).map((s) => (
          <tr key={s.id}>
            <td className="px-2 py-2">{s.name}</td>
            <td className="px-2 py-2">{s.folio ?? "—"}</td>
            <td className="px-2 py-2">{s.shares ?? "—"}</td>
            <td className="px-2 py-2">{s.percentage ?? "—"}</td>
          </tr>
        ))}
      </Table>
      {holders.data && (
        <p className="mt-2 text-xs text-slate-500">
          Total: {holders.data.total_shares} shares · {holders.data.total_percentage}%
        </p>
      )}
    </Card>
  );
}

function FyAttributes(props: { companyId: string }) {
  const queryClient = useQueryClient();
  const [fy, setFy] = useState(new Date().getFullYear() + (new Date().getMonth() >= 3 ? 1 : 0));
  const [error, setError] = useState<unknown>(null);
  const attrs = useQuery({
    queryKey: ["fy-attrs", props.companyId, fy],
    queryFn: () =>
      api.get<Record<string, number | boolean | null>>(
        `/companies/${props.companyId}/fy-attributes/${fy}`,
      ),
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.put(`/companies/${props.companyId}/fy-attributes/${fy}`, body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["fy-attrs", props.companyId, fy] });
    },
    onError: setError,
  });

  return (
    <Card title={`Per-FY facts (FY ending ${fy}) — used by the rules engine`}>
      <p className="mb-3 text-xs text-slate-500">
        Unknown values leave calendar rows flagged “confirm applicability” rather than guessing.
        Manager or Partner role required to edit.
      </p>
      <div className="mb-3 w-32">
        <Field label="FY (ending year)">
          <Input value={String(fy)} type="number" onChange={(v) => setFy(Number(v))} />
        </Field>
      </div>
      <ErrorText error={error} />
      <form
        className="grid grid-cols-3 gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const body: Record<string, unknown> = {};
          for (const key of ["turnover", "net_worth", "net_profit"]) {
            const value = f.get(key) as string;
            if (value !== "") body[key] = Number(value);
          }
          for (const key of ["has_tan", "has_gst_registration", "has_transfer_pricing"]) {
            const value = f.get(key) as string;
            if (value !== "unknown") body[key] = value === "yes";
          }
          save.mutate(body);
        }}
      >
        {(["turnover", "net_worth", "net_profit"] as const).map((key) => (
          <Field key={key} label={`${key.replace("_", " ")} (₹)`}>
            <Input name={key} type="number" defaultValue={attrs.data?.[key] != null ? String(attrs.data[key]) : ""} />
          </Field>
        ))}
        {(["has_tan", "has_gst_registration", "has_transfer_pricing"] as const).map((key) => (
          <Field key={key} label={key.replaceAll("_", " ")}>
            <select
              name={key}
              defaultValue={
                attrs.data?.[key] == null ? "unknown" : attrs.data[key] ? "yes" : "no"
              }
              className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm"
            >
              <option value="unknown">unknown</option>
              <option value="yes">yes</option>
              <option value="no">no</option>
            </select>
          </Field>
        ))}
        <div className="col-span-3">
          <Button type="submit">Save FY facts</Button>
        </div>
      </form>
    </Card>
  );
}
