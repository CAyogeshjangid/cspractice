import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import { Button, Card, ErrorText, Field, Input } from "../../components/ds";
import { useSession } from "../../app/session";

export function AuthPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [needsTotp, setNeedsTotp] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const session = useSession();
  const navigate = useNavigate();

  async function submit(form: FormData) {
    setError(null);
    try {
      const result =
        mode === "register"
          ? await api.post<{ role: string }>("/auth/register", {
              firm_name: form.get("firm_name"),
              email: form.get("email"),
              password: form.get("password"),
            })
          : await api.post<{ role: string }>("/auth/login", {
              email: form.get("email"),
              password: form.get("password"),
              totp_code: (form.get("totp_code") as string) || null,
            });
      session.signIn(result.role);
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError && err.message === "totp_required") {
        setNeedsTotp(true);
        setError(new Error("Enter the 6-digit code from your authenticator app."));
      } else {
        setError(err);
      }
    }
  }

  return (
    <div className="mx-auto mt-20 max-w-sm space-y-4">
      <h1 className="text-center text-2xl font-bold text-indigo-700">Praxis</h1>
      <Card title={mode === "register" ? "Register your firm" : "Sign in"}>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            void submit(new FormData(e.currentTarget));
          }}
        >
          {mode === "register" && (
            <Field label="Firm name">
              <Input name="firm_name" required minLength={2} />
            </Field>
          )}
          <Field label="Email">
            <Input name="email" type="email" required />
          </Field>
          <Field label="Password (min 12 characters)">
            <Input name="password" type="password" required minLength={12} />
          </Field>
          {needsTotp && (
            <Field label="Authenticator code">
              <Input name="totp_code" placeholder="123456" required minLength={6} />
            </Field>
          )}
          <ErrorText error={error} />
          <div className="flex items-center justify-between">
            <Button type="submit">{mode === "register" ? "Create firm" : "Sign in"}</Button>
            <button
              type="button"
              className="text-sm text-indigo-600 hover:underline"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setNeedsTotp(false);
                setError(null);
              }}
            >
              {mode === "login" ? "New firm? Register" : "Have an account? Sign in"}
            </button>
          </div>
        </form>
      </Card>
      <p className="text-center text-xs text-slate-400">
        The first registered user becomes the firm's Partner. Team members join by invitation.
      </p>
    </div>
  );
}

export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const [error, setError] = useState<unknown>(null);
  const session = useSession();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";

  return (
    <div className="mx-auto mt-20 max-w-sm space-y-4">
      <Card title="Join your firm on Praxis">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            api
              .post<{ role: string }>("/team/invitations/accept", {
                token: form.get("token"),
                password: form.get("password"),
              })
              .then((result) => {
                session.signIn(result.role);
                navigate("/");
              })
              .catch(setError);
          }}
        >
          <Field label="Invitation token">
            <Input name="token" defaultValue={token} required minLength={20} />
          </Field>
          <Field label="Choose a password (min 12 characters)">
            <Input name="password" type="password" required minLength={12} />
          </Field>
          <ErrorText error={error} />
          <Button type="submit">Join firm</Button>
        </form>
      </Card>
    </div>
  );
}
