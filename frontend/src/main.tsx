import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import { AppShell } from "./components/AppShell";
import { OverviewPage } from "./pages/OverviewPage";
import { MonitorsPage } from "./pages/MonitorsPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { MonitorDetailPage } from "./pages/MonitorDetailPage";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<OverviewPage />} />
          <Route path="monitors" element={<MonitorsPage />} />
          <Route path="monitors/:id" element={<MonitorDetailPage />} />
          <Route path="incidents" element={<IncidentsPage />} />
          <Route path="*" element={<OverviewPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
