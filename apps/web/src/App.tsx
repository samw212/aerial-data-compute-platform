import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useMe } from "./api/queries";
import { Login } from "./stages/Login";
import { Portfolio } from "./stages/Portfolio";
import { VenuePage } from "./stages/Venue";
import { ModelStage } from "./stages/Model";
import { PlanStage } from "./stages/Plan";
import { ReportStage } from "./stages/Report";
import { CaptureStage, ProcessStage } from "./stages/CaptureProcess";
import { AdminPage, JobsPage } from "./stages/System";

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

function Guard() {
  const me = useMe();
  if (me.isLoading) return <div style={{ padding: 24, color: "var(--color-ink-3)" }} className="m">…</div>;
  if (me.isError) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Guard />}>
            <Route path="/" element={<Portfolio />} />
            <Route path="/venues/:venueId" element={<VenuePage />} />
            <Route path="/venues/:venueId/surveys/:surveyId/capture" element={<CaptureStage />} />
            <Route path="/venues/:venueId/surveys/:surveyId/process" element={<ProcessStage />} />
            <Route path="/venues/:venueId/surveys/:surveyId/model" element={<ModelStage />} />
            <Route path="/venues/:venueId/scenarios/:scenarioId/plan" element={<PlanStage />} />
            <Route path="/venues/:venueId/scenarios/:scenarioId/report" element={<ReportStage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
