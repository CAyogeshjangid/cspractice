import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../../api/client";
import type { DeadLetter, DscReminderPolicy, Invitation, TeamMember } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Select, Table } from "../../components/ds";

export function TeamPage() {
  return (
    <div className="space-y-4">
      <Members />
      <Invitations />
      <DeadLetterView />
      <EmailSettings />
      <DscReminderSettings />
    </div>
  );
}

function Members() {
  const members = useQuery({
    queryKey: ["members"],
    queryFn: () => api.get<TeamMember[]>("/team/members"),
  });
  return (
    <Card title="Team">
      <Table headers={["Email", "Role", "Status"]}>
        {(members.data ?? []).map((m) => (
          <tr key={m.id}>
            <td className="px-2 py-2">{m.email}</td>
            <td className="px-2 py-2">
              <Badge tone="info">{m.role}</Badge>
            </td>
            <td className="px-2 py-2">
              {m.is_active ? <Badge tone="ok">active</Badge> : <Badge>disabled</Badge>}
            </td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function Invitations() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [issued, setIssued] = useState<{ token: string; email: string } | null>(null);
  const [role, setRole] = useState("executive");
  const invitations = useQuery({
    queryKey: ["invitations"],
    queryFn: () => api.get<Invitation[]>("/team/invitations"),
    retry: false,
  });
  const invite = useMutation({
    mutationFn: (body: { email: string; role: string }) =>
      api.post<{ token: string }>("/team/invitations", body),
    onSuccess: (result, vars) => {
      setIssued({ token: result.token, email: vars.email });
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["invitations"] });
    },
    onError: setError,
  });

  const forbidden =
    invitations.error instanceof ApiError && invitations.error.status === 403;
  if (forbidden) return null; // Partner-only section

  return (
    <Card title="Invitations (Partner only)">
      <ErrorText error={error} />
      {issued && (
        <div className="mb-3 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">
          <p className="font-medium">Invitation for {issued.email} — share this link once:</p>
          <code className="break-all text-xs">
            {window.location.origin}/accept?token={issued.token}
          </code>
          <p className="mt-1 text-xs">
            Shown once only — only a hash is stored. Email delivery of invitations arrives with
            the notification pipeline.
          </p>
        </div>
      )}
      <form
        className="mb-3 flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          invite.mutate({ email: f.get("email") as string, role });
          e.currentTarget.reset();
        }}
      >
        <Field label="Email">
          <Input name="email" type="email" required />
        </Field>
        <Field label="Role">
          <Select
            value={role}
            onChange={setRole}
            options={["manager", "executive", "viewer"].map((r) => ({ value: r, label: r }))}
          />
        </Field>
        <Button type="submit">Invite</Button>
      </form>
      <Table headers={["Email", "Role", "Expires", "Status"]}>
        {(invitations.data ?? []).map((i) => (
          <tr key={i.id}>
            <td className="px-2 py-2">{i.email}</td>
            <td className="px-2 py-2">{i.role}</td>
            <td className="px-2 py-2 text-xs">{new Date(i.expires_at).toLocaleDateString()}</td>
            <td className="px-2 py-2">
              {i.accepted_at ? <Badge tone="ok">accepted</Badge> : <Badge tone="warn">pending</Badge>}
            </td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function DeadLetterView() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const items = useQuery({
    queryKey: ["dead-letter"],
    queryFn: () => api.get<DeadLetter[]>("/reminders/dead-letter"),
    retry: false,
  });
  const retry = useMutation({
    mutationFn: (id: string) => api.post(`/reminders/${id}/retry`),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["dead-letter"] });
    },
    onError: setError,
  });

  const forbidden = items.error instanceof ApiError && items.error.status === 403;
  if (forbidden) return null; // Manager+ section

  return (
    <Card title="Reminder failures (dead letter)">
      <ErrorText error={error} />
      {items.data?.length === 0 ? (
        <Empty>No failed reminder dispatches — good.</Empty>
      ) : (
        <Table headers={["Scheduled", "Subject", "Status", "Attempts", "Error", ""]}>
          {(items.data ?? []).map((d) => (
            <tr key={d.id}>
              <td className="px-2 py-2">{d.scheduled_for}</td>
              <td className="px-2 py-2 text-xs">
                {d.subject_kind === "dsc_token" ? (
                  <>
                    <Badge tone="info">DSC</Badge> {d.subject_label}
                  </>
                ) : (
                  <Badge>calendar</Badge>
                )}
              </td>
              <td className="px-2 py-2">
                <Badge tone="warn">{d.status}</Badge>
              </td>
              <td className="px-2 py-2">{d.attempt_count}</td>
              <td className="px-2 py-2 text-xs text-rose-700">{d.error}</td>
              <td className="px-2 py-2 text-right">
                <Button variant="ghost" onClick={() => retry.mutate(d.id)}>
                  Retry
                </Button>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

function EmailSettings() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [provider, setProvider] = useState("smtp");
  const settings = useQuery({
    queryKey: ["email-settings"],
    queryFn: () =>
      api.get<{ provider: string | null; from_addr: string | null; host: string | null;
                port: number | null; username: string | null; has_password: boolean;
                has_api_key: boolean }>("/firm/email-settings"),
    retry: false,
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.put("/firm/email-settings", body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["email-settings"] });
    },
    onError: setError,
  });

  const forbidden = settings.error instanceof ApiError && settings.error.status === 403;
  if (forbidden) return null; // Partner-only section

  return (
    <Card title="Reminder email provider (Partner only — secrets stored encrypted)">
      <ErrorText error={error} />
      {settings.data?.provider && (
        <p className="mb-2 text-sm text-slate-600">
          Configured: <Badge tone="ok">{settings.data.provider}</Badge> from{" "}
          {settings.data.from_addr}
          {settings.data.has_password || settings.data.has_api_key ? " (secret set)" : ""}
        </p>
      )}
      <form
        className="grid grid-cols-3 gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const body: Record<string, unknown> = {
            provider,
            from_addr: f.get("from_addr"),
          };
          if (provider === "smtp") {
            body.host = f.get("host");
            body.port = Number(f.get("port"));
            body.username = (f.get("username") as string) || null;
            const password = f.get("password") as string;
            if (password) body.password = password;
          } else {
            body.api_key = f.get("api_key");
          }
          save.mutate(body);
        }}
      >
        <Field label="Provider">
          <Select
            value={provider}
            onChange={setProvider}
            options={[
              { value: "smtp", label: "SMTP" },
              { value: "resend", label: "Resend" },
            ]}
          />
        </Field>
        <Field label="From address">
          <Input name="from_addr" type="email" required />
        </Field>
        {provider === "smtp" ? (
          <>
            <Field label="Host">
              <Input name="host" required />
            </Field>
            <Field label="Port">
              <Input name="port" type="number" required />
            </Field>
            <Field label="Username">
              <Input name="username" />
            </Field>
            <Field label="Password (write-only)">
              <Input name="password" type="password" />
            </Field>
          </>
        ) : (
          <Field label="Resend API key (write-only)">
            <Input name="api_key" type="password" required />
          </Field>
        )}
        <div className="col-span-3">
          <Button type="submit">Save provider</Button>
        </div>
      </form>
    </Card>
  );
}

function DscReminderSettings() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const policy = useQuery({
    queryKey: ["dsc-reminders"],
    queryFn: () => api.get<DscReminderPolicy>("/firm/dsc-reminders"),
  });
  const save = useMutation({
    mutationFn: (body: DscReminderPolicy) => api.put("/firm/dsc-reminders", body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["dsc-reminders"] });
    },
    onError: setError,
  });

  return (
    <Card title="DSC expiry reminders (Partner only)">
      <p className="mb-2 text-sm text-slate-600">
        Email the recipients below this many days before any DSC token expires. Recipients are a
        firm-wide list — DSC tokens have no individual owner. Uses the same email provider,
        retry and dead-letter handling as calendar reminders.
      </p>
      <ErrorText error={error} />
      <form
        className="grid grid-cols-2 gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const days = String(f.get("days_before") ?? "")
            .split(",")
            .map((s) => Number(s.trim()))
            .filter((n) => Number.isFinite(n) && n >= 0);
          const recipients = String(f.get("recipients") ?? "")
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean);
          save.mutate({ days_before: days, recipients });
        }}
      >
        <Field label="Days before expiry (comma-separated)">
          <Input
            name="days_before"
            defaultValue={(policy.data?.days_before ?? []).join(", ")}
            placeholder="30, 7"
          />
        </Field>
        <Field label="Recipient emails (comma-separated)">
          <Input
            name="recipients"
            defaultValue={(policy.data?.recipients ?? []).join(", ")}
            placeholder="compliance@firm.example"
          />
        </Field>
        <div className="col-span-2">
          <Button type="submit">Save DSC reminder policy</Button>
        </div>
      </form>
    </Card>
  );
}
