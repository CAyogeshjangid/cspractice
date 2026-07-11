import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import type { CalendarRow, TeamMember } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Table } from "../../components/ds";
import { useSession } from "../../app/session";

function currentFy(): number {
  const now = new Date();
  return now.getFullYear() + (now.getMonth() >= 3 ? 1 : 0); // Indian FY ends 31 Mar
}

export function CalendarPage() {
  const session = useSession();
  const queryClient = useQueryClient();
  const [fy, setFy] = useState(currentFy());
  const [reviewOnly, setReviewOnly] = useState(false);
  const [openRow, setOpenRow] = useState<CalendarRow | null>(null);
  const [error, setError] = useState<unknown>(null);
  const company = session.workingCompany;

  const rows = useQuery({
    enabled: !!company,
    queryKey: ["calendar", company?.id, fy, reviewOnly],
    queryFn: () =>
      api.get<CalendarRow[]>(
        `/companies/${company!.id}/calendar?fy=${fy}${reviewOnly ? "&needs_review=true" : ""}`,
      ),
  });

  const generate = useMutation({
    mutationFn: () => api.post(`/companies/${company!.id}/calendar/generate?fy=${fy}`),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["calendar", company?.id] });
    },
    onError: setError,
  });

  if (!company) {
    return <Empty>Select a working company in the sidebar to view its calendar.</Empty>;
  }

  const reviewCount = (rows.data ?? []).filter((r) => r.needs_review).length;

  return (
    <div className="space-y-4">
      <Card
        title={`Compliance calendar — ${company.name} — FY ${fy - 1}-${String(fy).slice(2)}`}
        actions={
          <>
            <Input value={String(fy)} type="number" onChange={(v) => setFy(Number(v))} />
            <Button variant="ghost" onClick={() => setReviewOnly(!reviewOnly)}>
              {reviewOnly ? "All rows" : `Review queue (${reviewCount})`}
            </Button>
            <Button onClick={() => generate.mutate()}>Generate / refresh</Button>
            <a
              className="px-1 py-1.5 text-sm text-indigo-600 hover:underline"
              href={`/api/v1/companies/${company.id}/calendar/export?fy=${fy}`}
            >
              Excel
            </a>
            <a
              className="px-1 py-1.5 text-sm text-indigo-600 hover:underline"
              href={`/api/v1/companies/${company.id}/calendar/export-word?fy=${fy}`}
            >
              Word
            </a>
          </>
        }
      >
        <ErrorText error={error} />
        {rows.data?.length === 0 ? (
          <Empty>
            No rows for this FY. Generate the calendar — rows appear once the signed rules
            dataset is loaded.
          </Empty>
        ) : (
          <Table headers={["Obligation", "Category", "Due", "Status", "Assignee", "Trace", ""]}>
            {(rows.data ?? []).map((r) => (
              <tr key={r.id} className={r.needs_review ? "bg-amber-50" : ""}>
                <td className="px-2 py-2">
                  {r.obligation_name}
                  {r.occurrence_label && (
                    <span className="ml-1 text-xs text-slate-400">[{r.occurrence_label}]</span>
                  )}
                  {r.needs_review && (
                    <div className="text-xs text-amber-700">⚑ {r.needs_review_reason}</div>
                  )}
                </td>
                <td className="px-2 py-2">
                  <Badge tone="info">{r.category}</Badge>
                </td>
                <td className="px-2 py-2">
                  {r.effective_due_date ?? <Badge tone="warn">needs review</Badge>}
                  {r.override_date && <div className="text-xs text-slate-400">override</div>}
                  {r.extension_date && !r.override_date && (
                    <div className="text-xs text-slate-400">extended ({r.extension_ref})</div>
                  )}
                </td>
                <td className="px-2 py-2">
                  <Badge tone={r.status === "filed" ? "ok" : r.status === "pending" ? "muted" : "info"}>
                    {r.status}
                  </Badge>
                </td>
                <td className="px-2 py-2 text-xs">{r.assignee_user_id ? "assigned" : "—"}</td>
                <td className="px-2 py-2">
                  <TracePopover row={r} />
                </td>
                <td className="px-2 py-2 text-right">
                  <button
                    className="text-sm text-indigo-600 hover:underline"
                    onClick={() => setOpenRow(r)}
                  >
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      {openRow && (
        <RowEditor
          row={openRow}
          onClose={() => {
            setOpenRow(null);
            void queryClient.invalidateQueries({ queryKey: ["calendar", company.id] });
          }}
        />
      )}
    </div>
  );
}

function TracePopover(props: { row: CalendarRow }) {
  const r = props.row;
  return (
    <details className="text-xs">
      <summary className="cursor-pointer text-slate-500 hover:text-indigo-600">
        {r.rule_code} v{r.rule_version}
      </summary>
      <div className="mt-1 w-64 rounded-md border border-slate-200 bg-white p-2 shadow">
        <p>
          <b>Rule:</b> {r.rule_code} (version {r.rule_version})
        </p>
        <p>
          <b>Citation:</b> {r.citation}
        </p>
        <p>
          <b>Computed:</b> {r.computed_due_date ?? "—"}
        </p>
        {r.extension_date && (
          <p>
            <b>Extension:</b> {r.extension_date} ({r.extension_ref})
          </p>
        )}
        {r.override_date && (
          <p>
            <b>Override:</b> {r.override_date} — {r.override_reason}
          </p>
        )}
        {r.form_number && (
          <p>
            <b>Form:</b> {r.form_number}
          </p>
        )}
      </div>
    </details>
  );
}

function RowEditor(props: { row: CalendarRow; onClose: () => void }) {
  const r = props.row;
  const [error, setError] = useState<unknown>(null);
  const members = useQuery({
    queryKey: ["members"],
    queryFn: () => api.get<TeamMember[]>("/team/members"),
  });
  const reminders = useQuery({
    queryKey: ["reminders", r.id],
    queryFn: () =>
      api.get<{ days_before: number[]; extra_emails: string[] }>(
        `/calendar-rows/${r.id}/reminders`,
      ),
  });

  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch(`/calendar-rows/${r.id}`, body),
    onSuccess: props.onClose,
    onError: setError,
  });
  const saveReminders = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.put(`/calendar-rows/${r.id}/reminders`, body),
    onSuccess: props.onClose,
    onError: setError,
  });

  return (
    <Card
      title={`Edit: ${r.obligation_name}`}
      actions={
        <Button variant="ghost" onClick={props.onClose}>
          Close
        </Button>
      }
    >
      <ErrorText error={error} />
      <div className="grid grid-cols-2 gap-6">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            const body: Record<string, unknown> = {
              status: f.get("status"),
              remarks: (f.get("remarks") as string) || null,
              assignee_user_id: (f.get("assignee") as string) || null,
            };
            const srn = f.get("srn") as string;
            if (srn) body.srn = srn;
            if (f.get("filed_offline_ack") === "on") body.filed_offline_ack = true;
            const overrideDate = f.get("override_date") as string;
            if (overrideDate) {
              body.override_date = overrideDate;
              body.override_reason = f.get("override_reason");
            }
            if (f.get("acknowledge_review") === "on") body.acknowledge_review = true;
            patch.mutate(body);
          }}
        >
          <h3 className="text-sm font-semibold">Status & assignment</h3>
          <Field label="Status">
            <select name="status" defaultValue={r.status} className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm">
              {["pending", "in_progress", "filed", "not_applicable"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </Field>
          <Field label="SRN (required to mark filed, unless filed offline)">
            <Input name="srn" defaultValue={r.srn ?? ""} />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" name="filed_offline_ack" defaultChecked={r.filed_offline_ack} />
            Filed offline (no SRN)
          </label>
          <Field label="Assignee">
            <select name="assignee" defaultValue={r.assignee_user_id ?? ""} className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm">
              <option value="">— unassigned —</option>
              {(members.data ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.email} ({m.role})
                </option>
              ))}
            </select>
          </Field>
          <Field label="Remarks">
            <Input name="remarks" defaultValue={r.remarks ?? ""} />
          </Field>
          <h3 className="pt-2 text-sm font-semibold">Override (Manager+, reason required)</h3>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Override date">
              <Input name="override_date" type="date" defaultValue={r.override_date ?? ""} />
            </Field>
            <Field label="Reason">
              <Input name="override_reason" defaultValue={r.override_reason ?? ""} />
            </Field>
          </div>
          {r.needs_review && (
            <label className="flex items-center gap-2 text-sm text-amber-700">
              <input type="checkbox" name="acknowledge_review" />
              Reviewed — clear the “{r.needs_review_reason}” flag
            </label>
          )}
          <Button type="submit">Save row</Button>
        </form>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            saveReminders.mutate({
              days_before: (f.get("days_before") as string)
                .split(",")
                .map((s) => Number(s.trim()))
                .filter((n) => !Number.isNaN(n)),
              extra_emails: (f.get("extra_emails") as string)
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            });
          }}
        >
          <h3 className="text-sm font-semibold">Email reminders</h3>
          <Field label="Days before due (comma-separated, e.g. 30,15,7,1)">
            <Input
              name="days_before"
              defaultValue={(reminders.data?.days_before ?? []).join(", ")}
            />
          </Field>
          <Field label="Extra recipient emails (comma-separated)">
            <Input
              name="extra_emails"
              defaultValue={(reminders.data?.extra_emails ?? []).join(", ")}
            />
          </Field>
          <p className="text-xs text-slate-500">
            Reminders go to the assignee plus any extra emails. Failures appear in the
            dead-letter view under Team & Settings.
          </p>
          <Button type="submit">Save reminders</Button>
        </form>
      </div>
    </Card>
  );
}
