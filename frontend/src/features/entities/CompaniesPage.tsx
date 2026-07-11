import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { Company, ImportReport } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Table } from "../../components/ds";

export function CompaniesPage() {
  const queryClient = useQueryClient();
  const companies = useQuery({
    queryKey: ["companies"],
    queryFn: () => api.get<Company[]>("/companies"),
  });
  const [showAdd, setShowAdd] = useState(false);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<unknown>(null);

  const importFile = useMutation({
    mutationFn: async ({ file, dryRun }: { file: File; dryRun: boolean }) => {
      const form = new FormData();
      form.append("file", file);
      return api.upload<ImportReport>(`/companies/import?dry_run=${dryRun}`, form);
    },
    onSuccess: (result) => {
      setReport(result);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: (err) => {
      // 422 carries the row-level validation report
      const detail = (err as { detail?: ImportReport }).detail;
      if (detail && Array.isArray(detail.errors)) setReport(detail);
      setError(err);
    },
  });

  const addCompany = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<Company>("/companies", body),
    onSuccess: () => {
      setShowAdd(false);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: setError,
  });

  return (
    <div className="space-y-4">
      <Card
        title={`Companies (${companies.data?.length ?? 0})`}
        actions={
          <>
            <a href="/api/v1/companies/import/template" className="text-sm text-indigo-600 hover:underline">
              Import template
            </a>
            <a href="/api/v1/companies/export" className="text-sm text-indigo-600 hover:underline">
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
                  if (file) importFile.mutate({ file, dryRun: false });
                  e.target.value = "";
                }}
              />
            </label>
            <Button onClick={() => setShowAdd(!showAdd)} variant="ghost">
              {showAdd ? "Close" : "Add company"}
            </Button>
          </>
        }
      >
        <ErrorText error={error} />
        {report && (
          <div className="mb-3 rounded-md bg-slate-50 p-3 text-sm">
            {report.errors.length === 0 ? (
              <p className="text-emerald-700">
                Imported: {report.created ?? 0} created, {report.updated ?? 0} updated,{" "}
                {report.restored ?? 0} restored, {report.unchanged ?? 0} unchanged.
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
        {showAdd && (
          <form
            className="mb-4 grid grid-cols-2 gap-3 rounded-md bg-slate-50 p-3"
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              addCompany.mutate({
                cin: form.get("cin"),
                name: form.get("name"),
                agm_date: (form.get("agm_date") as string) || null,
                registered_address: (form.get("registered_address") as string) || null,
              });
            }}
          >
            <Field label="CIN (21 characters)">
              <Input name="cin" required minLength={21} maxLength={21} />
            </Field>
            <Field label="Company name">
              <Input name="name" required />
            </Field>
            <Field label="AGM date">
              <Input name="agm_date" type="date" />
            </Field>
            <Field label="Registered address">
              <Input name="registered_address" />
            </Field>
            <div className="col-span-2">
              <Button type="submit">Save company</Button>
            </div>
          </form>
        )}
        {companies.data?.length === 0 ? (
          <Empty>No companies yet — import your portfolio from Excel to get started.</Empty>
        ) : (
          <Table headers={["Name", "CIN", "AGM date", "Status", ""]}>
            {(companies.data ?? []).map((c) => (
              <tr key={c.id} className="hover:bg-slate-50">
                <td className="px-2 py-2 font-medium">{c.name}</td>
                <td className="px-2 py-2 font-mono text-xs">{c.cin}</td>
                <td className="px-2 py-2">{c.agm_date ?? "—"}</td>
                <td className="px-2 py-2">
                  {c.is_listed ? <Badge tone="info">listed</Badge> : <Badge>unlisted</Badge>}
                </td>
                <td className="px-2 py-2 text-right">
                  <Link to={`/companies/${c.id}`} className="text-indigo-600 hover:underline">
                    Open →
                  </Link>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
