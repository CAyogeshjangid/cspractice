/** Auth session + working-company context (PRD §3: selection is a UI
 * convenience only — authorization is always server-side per request). */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api/client";
import type { Company } from "../api/types";

interface Session {
  role: string | null; // null = not signed in (or unknown yet)
  ready: boolean;
  signIn: (role: string) => void;
  signOut: () => Promise<void>;
  workingCompany: Company | null;
  setWorkingCompany: (c: Company | null) => void;
}

const Ctx = createContext<Session>(null as unknown as Session);

export function SessionProvider(props: { children: ReactNode }) {
  const [role, setRole] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [workingCompany, setWorkingCompanyState] = useState<Company | null>(null);

  useEffect(() => {
    // probe an authenticated endpoint to restore the session on reload
    api
      .get<{ id: string }[]>("/team/members")
      .then((members) => {
        setRole(members.length ? "member" : null);
        setReady(true);
      })
      .catch(() => {
        setRole(null);
        setReady(true);
      });
  }, []);

  const signOut = useCallback(async () => {
    await api.post("/auth/logout");
    setRole(null);
    setWorkingCompanyState(null);
  }, []);

  const setWorkingCompany = useCallback((c: Company | null) => {
    setWorkingCompanyState(c);
  }, []);

  return (
    <Ctx.Provider
      value={{ role, ready, signIn: setRole, signOut, workingCompany, setWorkingCompany }}
    >
      {props.children}
    </Ctx.Provider>
  );
}

export function useSession(): Session {
  return useContext(Ctx);
}
