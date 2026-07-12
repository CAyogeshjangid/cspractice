import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import type { Director } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Select, Table } from "../../components/ds";
import { useSession } from "../../app/session";

interface Meeting {
  id: string;
  fy: number;
  meeting_type: string;
  status: string;
  meeting_date: string;
  meeting_time: string;
  venue: string;
  chairperson: string | null;
  agenda_items: string[];
  participant_director_ids: string[];
}

function currentFy(): number {
  const now = new Date();
  return now.getFullYear() + (now.getMonth() >= 3 ? 1 : 0);
}

export function MeetingsPage() {
  const session = useSession();
  const queryClient = useQueryClient();
  const [fy, setFy] = useState(currentFy());
  const [error, setError] = useState<unknown>(null);
  const [showForm, setShowForm] = useState(false);
  const [packFor, setPackFor] = useState<Meeting | null>(null);
  const company = session.workingCompany;

  const meetings = useQuery({
    enabled: !!company,
    queryKey: ["meetings", company?.id, fy],
    queryFn: () => api.get<Meeting[]>(`/companies/${company!.id}/meetings?fy=${fy}`),
  });
  const directors = useQuery({
    enabled: !!company,
    queryKey: ["directors", company?.id],
    queryFn: () => api.get<Director[]>(`/companies/${company!.id}/directors`),
  });

  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post(`/companies/${company!.id}/meetings`, body),
    onSuccess: () => {
      setShowForm(false);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["meetings", company?.id] });
    },
    onError: setError,
  });

  if (!company) {
    return <Empty>Select a working company in the sidebar to schedule meetings.</Empty>;
  }

  return (
    <div className="space-y-4">
      <Card
        title={`Meetings — ${company.name} — FY ${fy - 1}-${String(fy).slice(2)}`}
        actions={
          <>
            <Input value={String(fy)} type="number" onChange={(v) => setFy(Number(v))} />
            <Button onClick={() => setShowForm(!showForm)}>
              {showForm ? "Close" : "Schedule meeting"}
            </Button>
          </>
        }
      >
        <ErrorText error={error} />
        {showForm && (
          <form
            className="mb-4 grid grid-cols-3 gap-3 rounded-md bg-slate-50 p-3"
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              create.mutate({
                fy,
                meeting_type: f.get("meeting_type"),
                meeting_date: f.get("meeting_date"),
                meeting_time: f.get("meeting_time"),
                venue: f.get("venue"),
                notice_date: (f.get("notice_date") as string) || null,
                chairperson: (f.get("chairperson") as string) || null,
                agenda_items: (f.get("agenda") as string)
                  .split("\n").map((s) => s.trim()).filter(Boolean),
                participant_director_ids: f.getAll("participants") as string[],
              });
            }}
          >
            <Field label="Type">
              <select name="meeting_type" className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm">
                <option value="board">Board Meeting</option>
                <option value="committee">Committee Meeting</option>
                <option value="egm">EGM</option>
                <option value="agm">AGM</option>
              </select>
            </Field>
            <Field label="Date">
              <Input name="meeting_date" type="date" required />
            </Field>
            <Field label="Time">
              <Input name="meeting_time" placeholder="11:00 AM" required />
            </Field>
            <Field label="Venue">
              <Input name="venue" required />
            </Field>
            <Field label="Notice date">
              <Input name="notice_date" type="date" />
            </Field>
            <Field label="Chairperson">
              <Input name="chairperson" />
            </Field>
            <div className="col-span-2">
              <Field label="Agenda (one item per line)">
                <textarea name="agenda" rows={3}
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm" />
              </Field>
            </div>
            <Field label="Participants">
              <div className="max-h-28 space-y-1 overflow-y-auto text-sm">
                {(directors.data ?? []).map((d) => (
                  <label key={d.id} className="flex items-center gap-2">
                    <input type="checkbox" name="participants" value={d.id} defaultChecked />
                    {d.name}
                  </label>
                ))}
              </div>
            </Field>
            <div className="col-span-3">
              <Button type="submit">Save meeting</Button>
            </div>
          </form>
        )}
        {meetings.data?.length === 0 ? (
          <Empty>No meetings scheduled for this FY.</Empty>
        ) : (
          <Table headers={["Type", "Date", "Venue", "Agenda", "Status", ""]}>
            {(meetings.data ?? []).map((m) => (
              <tr key={m.id}>
                <td className="px-2 py-2">
                  <Badge tone="info">{m.meeting_type.toUpperCase()}</Badge>
                </td>
                <td className="px-2 py-2">
                  {m.meeting_date} · {m.meeting_time}
                </td>
                <td className="px-2 py-2 text-xs">{m.venue}</td>
                <td className="px-2 py-2 text-xs">{m.agenda_items.length} items</td>
                <td className="px-2 py-2">
                  <Badge tone={m.status === "held" ? "ok" : "muted"}>{m.status}</Badge>
                </td>
                <td className="px-2 py-2 text-right">
                  <button
                    className="text-sm text-indigo-600 hover:underline"
                    onClick={() => setPackFor(m)}
                  >
                    Generate pack →
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      {packFor && <PackDialog meeting={packFor} onClose={() => setPackFor(null)} />}
    </div>
  );
}

function PackDialog(props: { meeting: Meeting; onClose: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const [letterhead, setLetterhead] = useState("company");
  const [result, setResult] = useState<{ template_code: string; download: string }[] | null>(null);
  const generate = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<{ documents: { template_code: string; download: string }[] }>(
        `/meetings/${props.meeting.id}/pack`, body),
    onSuccess: (r) => {
      setResult(r.documents);
      setError(null);
    },
    onError: setError,
  });

  return (
    <Card
      title={`Document pack — ${props.meeting.meeting_type.toUpperCase()} on ${props.meeting.meeting_date}`}
      actions={<Button variant="ghost" onClick={props.onClose}>Close</Button>}
    >
      <ErrorText error={error} />
      {result ? (
        <ul className="space-y-1 text-sm">
          {result.map((d) => (
            <li key={d.template_code}>
              <a href={d.download} className="text-indigo-600 hover:underline">
                {d.template_code}.docx — download
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <form
          className="flex items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            generate.mutate({
              letterhead,
              signatory_name: f.get("signatory_name"),
              signatory_designation: f.get("signatory_designation"),
              place: f.get("place"),
            });
          }}
        >
          <Field label="Letterhead">
            <Select
              value={letterhead}
              onChange={setLetterhead}
              options={[
                { value: "company", label: "Company" },
                { value: "pcs", label: "PCS firm" },
                { value: "none", label: "None" },
              ]}
            />
          </Field>
          <Field label="Signatory">
            <Input name="signatory_name" required />
          </Field>
          <Field label="Designation">
            <Input name="signatory_designation" required />
          </Field>
          <Field label="Place">
            <Input name="place" required />
          </Field>
          <Button type="submit">Generate Notice + Minutes + Attendance</Button>
        </form>
      )}
      <p className="mt-2 text-xs text-slate-500">
        Attendance lists only the selected participants, resolved from the directors register.
        All templates must carry a current validation stamp.
      </p>
    </Card>
  );
}
