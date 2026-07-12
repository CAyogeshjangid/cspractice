import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import type { DocTemplate, GeneratedDoc } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Select, Table } from "../../components/ds";
import { useSession } from "../../app/session";

export function DocumentsPage() {
  const session = useSession();
  const company = session.workingCompany;

  return (
    <div className="space-y-4">
      <Templates />
      {company ? (
        <>
          <Generator companyId={company.id} companyName={company.name} />
          <Library companyId={company.id} />
        </>
      ) : (
        <Empty>Select a working company in the sidebar to generate documents.</Empty>
      )}
    </div>
  );
}

function Templates() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [stamping, setStamping] = useState<string | null>(null);
  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: () => api.get<DocTemplate[]>("/templates"),
  });
  const validate = useMutation({
    mutationFn: ({ code, body }: { code: string; body: Record<string, unknown> }) =>
      api.put(`/templates/${code}/validate`, body),
    onSuccess: () => {
      setStamping(null);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["templates"] });
    },
    onError: setError,
  });

  return (
    <Card title="Templates (validation stamps are enforced — unstamped templates refuse to generate)">
      <ErrorText error={error} />
      <Table headers={["Code", "Name", "Governing ref", "Version", "Stamp", ""]}>
        {(templates.data ?? []).map((t) => (
          <tr key={t.code}>
            <td className="px-2 py-2 font-mono text-xs">{t.code}</td>
            <td className="px-2 py-2">{t.name}</td>
            <td className="px-2 py-2 text-xs">{t.governing_reference}</td>
            <td className="px-2 py-2">v{t.version}</td>
            <td className="px-2 py-2">
              {t.validated ? (
                <Badge tone="ok">✓ {t.validated_by}</Badge>
              ) : (
                <Badge tone="warn">unstamped</Badge>
              )}
            </td>
            <td className="px-2 py-2 text-right">
              <button
                className="text-sm text-indigo-600 hover:underline"
                onClick={() => setStamping(stamping === t.code ? null : t.code)}
              >
                {t.validated ? "Re-stamp" : "Stamp"}
              </button>
            </td>
          </tr>
        ))}
      </Table>
      {stamping && (
        <form
          className="mt-3 flex items-end gap-2 rounded-md bg-slate-50 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            validate.mutate({
              code: stamping,
              body: { validated_by: f.get("validated_by"), membership_no: f.get("membership_no") },
            });
          }}
        >
          <Field label={`Reviewing professional for ${stamping}`}>
            <Input name="validated_by" required minLength={3} />
          </Field>
          <Field label="Membership no.">
            <Input name="membership_no" required />
          </Field>
          <Button type="submit">Apply stamp</Button>
        </form>
      )}
    </Card>
  );
}

const PARAM_HINTS: Record<string, string[]> = {
  "AGM-NOTICE": ["meeting_time", "venue", "ordinary_business (one per line)", "special_business"],
  "MEETING-MINUTES": ["meeting_type", "meeting_date", "meeting_time", "venue", "chairperson", "agenda_items (one per line)", "conclusion_time"],
  "ATTENDANCE-SHEET": ["meeting_type", "meeting_date", "venue"],
  "DIRECTORS-REPORT": ["revenue", "profit_before_tax", "profit_after_tax", "state_of_affairs", "dividend", "transfer_to_reserves", "board_meetings_held", "other_disclosures"],
  "SHORTER-NOTICE": ["meeting_label", "meeting_date", "meeting_time", "venue", "member_name", "folio_no", "shares_held"],
  "AUDITOR-APPOINTMENT": ["meeting_label", "meeting_date"],
  "MR-3": ["period_ended", "observations", "other_applicable_laws", "pcs_name", "pcs_membership_no", "pcs_cop_no"],
};
const LIST_PARAMS = new Set(["ordinary_business", "special_business", "agenda_items"]);
const COMMON = ["signatory_name", "signatory_designation", "place"];

function Generator(props: { companyId: string; companyName: string }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [code, setCode] = useState("AGM-NOTICE");
  const [letterhead, setLetterhead] = useState("company");
  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: () => api.get<DocTemplate[]>("/templates"),
  });
  const generate = useMutation({
    mutationFn: (params: Record<string, unknown>) =>
      api.post<{ id: string; download: string }>(`/companies/${props.companyId}/documents`, {
        template_code: code,
        letterhead,
        params,
      }),
    onSuccess: (result) => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["library", props.companyId] });
      window.open(result.download, "_blank");
    },
    onError: setError,
  });

  const fields = [...(PARAM_HINTS[code] ?? []), ...COMMON];

  return (
    <Card title={`Generate for ${props.companyName}`}>
      <ErrorText error={error} />
      <div className="mb-3 grid grid-cols-2 gap-3">
        <Field label="Document">
          <Select
            value={code}
            onChange={setCode}
            options={(templates.data ?? []).map((t) => ({
              value: t.code,
              label: `${t.name}${t.validated ? "" : " (unstamped)"}`,
            }))}
          />
        </Field>
        <Field label="Letterhead">
          <Select
            value={letterhead}
            onChange={setLetterhead}
            options={[
              { value: "company", label: "Company letterhead" },
              { value: "pcs", label: "PCS firm letterhead" },
              { value: "none", label: "No letterhead" },
            ]}
          />
        </Field>
      </div>
      <form
        className="grid grid-cols-3 gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const params: Record<string, unknown> = {};
          for (const field of fields) {
            const key = field.split(" ")[0];
            const raw = (f.get(key) as string) ?? "";
            params[key] = LIST_PARAMS.has(key)
              ? raw.split("\n").map((s) => s.trim()).filter(Boolean)
              : raw;
          }
          generate.mutate(params);
        }}
      >
        {fields.map((field) => {
          const key = field.split(" ")[0];
          return (
            <Field key={key} label={field}>
              {LIST_PARAMS.has(key) ? (
                <textarea name={key} rows={3} className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm" />
              ) : (
                <Input name={key} />
              )}
            </Field>
          );
        })}
        <div className="col-span-3">
          <Button type="submit">Generate .docx</Button>
        </div>
      </form>
    </Card>
  );
}

function Library(props: { companyId: string }) {
  const docs = useQuery({
    queryKey: ["library", props.companyId],
    queryFn: () => api.get<GeneratedDoc[]>(`/companies/${props.companyId}/documents`),
  });
  return (
    <Card title="Document library">
      {docs.data?.length === 0 ? (
        <Empty>No documents generated yet.</Empty>
      ) : (
        <Table headers={["Document", "Template", "Letterhead", "Generated", ""]}>
          {(docs.data ?? []).map((d) => (
            <tr key={d.id}>
              <td className="px-2 py-2">{d.template_name}</td>
              <td className="px-2 py-2 font-mono text-xs">
                {d.template_code} v{d.template_version}
              </td>
              <td className="px-2 py-2">{d.letterhead}</td>
              <td className="px-2 py-2 text-xs">{new Date(d.generated_at).toLocaleString()}</td>
              <td className="px-2 py-2 text-right">
                <a href={d.download} className="text-indigo-600 hover:underline">
                  Download
                </a>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
