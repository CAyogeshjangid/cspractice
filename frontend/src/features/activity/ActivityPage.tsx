import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../../api/client";
import { Badge, Card, Empty, Field, Input, Table } from "../../components/ds";

interface ActivityEntry {
  id: string;
  actor_email: string | null;
  entity_type: string;
  entity_id: string | null;
  action: string;
  diff: { before?: unknown; after?: unknown } | null;
  ip: string | null;
  created_at: string;
}

export function ActivityPage() {
  const [entityType, setEntityType] = useState("");
  const [action, setAction] = useState("");
  const query = new URLSearchParams();
  if (entityType) query.set("entity_type", entityType);
  if (action) query.set("action", action);

  const entries = useQuery({
    queryKey: ["activity", entityType, action],
    queryFn: () => api.get<ActivityEntry[]>(`/activity?${query.toString()}`),
    retry: false,
  });

  if (entries.error instanceof ApiError && entries.error.status === 403) {
    return <Empty>The activity log is visible to Partners and Managers only.</Empty>;
  }

  return (
    <Card title="Activity log (append-only — no entry can be edited or deleted)">
      <div className="mb-3 flex gap-3">
        <Field label="Entity type (e.g. company, calendar_row)">
          <Input value={entityType} onChange={setEntityType} placeholder="all" />
        </Field>
        <Field label="Action (e.g. create, update, soft_delete)">
          <Input value={action} onChange={setAction} placeholder="all" />
        </Field>
      </div>
      {entries.data?.length === 0 ? (
        <Empty>No entries match.</Empty>
      ) : (
        <Table headers={["When", "Actor", "Entity", "Action", "Diff", "IP"]}>
          {(entries.data ?? []).map((e) => (
            <tr key={e.id}>
              <td className="px-2 py-2 text-xs whitespace-nowrap">
                {new Date(e.created_at).toLocaleString()}
              </td>
              <td className="px-2 py-2 text-xs">{e.actor_email ?? "system"}</td>
              <td className="px-2 py-2">
                <Badge tone="info">{e.entity_type}</Badge>
              </td>
              <td className="px-2 py-2 text-xs font-medium">{e.action}</td>
              <td className="px-2 py-2">
                {e.diff && (e.diff.before || e.diff.after) ? (
                  <details className="text-xs">
                    <summary className="cursor-pointer text-slate-500">view</summary>
                    <pre className="mt-1 max-w-md overflow-x-auto rounded bg-slate-50 p-2">
                      {JSON.stringify(e.diff, null, 2)}
                    </pre>
                  </details>
                ) : (
                  <span className="text-xs text-slate-400">—</span>
                )}
              </td>
              <td className="px-2 py-2 text-xs text-slate-400">{e.ip ?? "—"}</td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
