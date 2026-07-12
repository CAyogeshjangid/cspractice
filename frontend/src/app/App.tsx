import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ActivityPage } from "../features/activity/ActivityPage";
import { AcceptInvitePage, AuthPage } from "../features/auth/AuthPage";
import { CalendarPage } from "../features/calendar/CalendarPage";
import { CompanyDetail } from "../features/entities/CompanyDetail";
import { CompaniesPage } from "../features/entities/CompaniesPage";
import { DocumentsPage } from "../features/documents/DocumentsPage";
import { RegistersPage } from "../features/registers/RegistersPage";
import { TeamPage } from "../features/team/TeamPage";
import { Layout } from "./Layout";
import { SessionProvider, useSession } from "./session";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function Guard(props: { children: React.ReactNode }) {
  const session = useSession();
  if (!session.ready) return <p className="p-8 text-sm text-slate-500">Loading…</p>;
  if (!session.role) return <Navigate to="/login" replace />;
  return <>{props.children}</>;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<AuthPage />} />
            <Route path="/accept" element={<AcceptInvitePage />} />
            <Route
              element={
                <Guard>
                  <Layout />
                </Guard>
              }
            >
              <Route path="/" element={<CompaniesPage />} />
              <Route path="/companies/:companyId" element={<CompanyDetail />} />
              <Route path="/calendar" element={<CalendarPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/registers" element={<RegistersPage />} />
              <Route path="/team" element={<TeamPage />} />
              <Route path="/activity" element={<ActivityPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </SessionProvider>
    </QueryClientProvider>
  );
}
