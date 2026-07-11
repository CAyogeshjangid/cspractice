import { useEffect, useState } from "react";
import { api, ApiError, type Company } from "../api/client";

type Screen = "login" | "register" | "companies";

export function App() {
  const [screen, setScreen] = useState<Screen>("login");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // if the access cookie is still valid, land on companies directly
    api<Company[]>("/companies")
      .then(() => setScreen("companies"))
      .catch(() => undefined);
  }, []);

  const authed = () => {
    setError(null);
    setScreen("companies");
  };
  const fail = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : "something went wrong");

  return (
    <main style={{ maxWidth: 720, margin: "3rem auto", fontFamily: "system-ui" }}>
      <h1>Praxis</h1>
      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
      {screen === "login" && (
        <AuthForm
          kind="login"
          onDone={authed}
          onError={fail}
          switchTo={() => setScreen("register")}
        />
      )}
      {screen === "register" && (
        <AuthForm
          kind="register"
          onDone={authed}
          onError={fail}
          switchTo={() => setScreen("login")}
        />
      )}
      {screen === "companies" && <Companies onError={fail} />}
    </main>
  );
}

function AuthForm(props: {
  kind: "login" | "register";
  onDone: () => void;
  onError: (e: unknown) => void;
  switchTo: () => void;
}) {
  const register = props.kind === "register";
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        const data = new FormData(e.currentTarget);
        try {
          await api(`/auth/${props.kind}`, {
            method: "POST",
            body: register
              ? {
                  firm_name: data.get("firm_name"),
                  email: data.get("email"),
                  password: data.get("password"),
                }
              : { email: data.get("email"), password: data.get("password") },
          });
          props.onDone();
        } catch (err) {
          props.onError(err);
        }
      }}
    >
      <h2>{register ? "Register your firm" : "Sign in"}</h2>
      {register && (
        <label>
          Firm name <input name="firm_name" required minLength={2} />
        </label>
      )}
      <label>
        Email <input name="email" type="email" required />
      </label>
      <label>
        Password <input name="password" type="password" required minLength={12} />
      </label>
      <button type="submit">{register ? "Create firm" : "Sign in"}</button>
      <button type="button" onClick={props.switchTo}>
        {register ? "Have an account? Sign in" : "New firm? Register"}
      </button>
    </form>
  );
}

function Companies(props: { onError: (e: unknown) => void }) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const load = () => api<Company[]>("/companies").then(setCompanies).catch(props.onError);
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section>
      <h2>Companies</h2>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const data = new FormData(form);
          try {
            await api("/companies", {
              method: "POST",
              body: { cin: data.get("cin"), name: data.get("name") },
            });
            form.reset();
            await load();
          } catch (err) {
            props.onError(err);
          }
        }}
      >
        <input name="cin" placeholder="CIN (21 chars)" required minLength={21} maxLength={21} />
        <input name="name" placeholder="Company name" required />
        <button type="submit">Add company</button>
      </form>
      <table>
        <thead>
          <tr>
            <th>CIN</th>
            <th>Name</th>
            <th>AGM date</th>
          </tr>
        </thead>
        <tbody>
          {companies.map((c) => (
            <tr key={c.id}>
              <td>{c.cin}</td>
              <td>{c.name}</td>
              <td>{c.agm_date ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
