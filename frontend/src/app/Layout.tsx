import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Company } from "../api/types";
import { Select } from "../components/ds";
import { useSession } from "./session";

const NAV = [
  { to: "/", label: "Companies" },
  { to: "/calendar", label: "Compliance Calendar" },
  { to: "/registers", label: "Statutory Registers" },
  { to: "/documents", label: "Documents" },
  { to: "/activity", label: "Activity Log" },
  { to: "/team", label: "Team & Settings" },
];

export function Layout() {
  const session = useSession();
  const navigate = useNavigate();
  const companies = useQuery({
    queryKey: ["companies"],
    queryFn: () => api.get<Company[]>("/companies"),
  });

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900">
      <aside className="flex w-60 flex-col border-r border-slate-200 bg-white">
        <div className="border-b border-slate-200 p-4">
          <h1 className="text-lg font-bold text-indigo-700">Praxis</h1>
          <p className="text-xs text-slate-500">CS practice management</p>
        </div>
        <div className="border-b border-slate-200 p-3">
          <p className="mb-1 text-xs font-medium uppercase text-slate-400">Working company</p>
          <Select
            value={session.workingCompany?.id ?? ""}
            onChange={(id) => {
              const company = companies.data?.find((c) => c.id === id) ?? null;
              session.setWorkingCompany(company);
            }}
            options={[
              { value: "", label: "— select —" },
              ...(companies.data ?? []).map((c) => ({ value: c.id, label: c.name })),
            ]}
          />
        </div>
        <nav className="flex-1 p-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm ${
                  isActive
                    ? "bg-indigo-50 font-medium text-indigo-700"
                    : "text-slate-600 hover:bg-slate-50"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button
          className="border-t border-slate-200 p-3 text-left text-sm text-slate-500 hover:bg-slate-50"
          onClick={() => {
            void session.signOut().then(() => navigate("/login"));
          }}
        >
          Sign out
        </button>
      </aside>
      <main className="flex-1 p-6">
        <Outlet />
      </main>
    </div>
  );
}
