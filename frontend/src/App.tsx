import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { CalibratePage } from "./pages/CalibratePage";
import { CameraDetailPage } from "./pages/CameraDetailPage";
import { CamerasPage } from "./pages/CamerasPage";
import { EventDetailPage } from "./pages/EventDetailPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { JobsPage } from "./pages/JobsPage";
import { LoginPage } from "./pages/LoginPage";
import { ObjectsPage } from "./pages/ObjectsPage";
import { OverviewPage } from "./pages/OverviewPage";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

function ProtectedApp() {
  return (
    <RequireAuth>\n      <Layout>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/jobs/:jobId" element={<JobDetailPage />} />
          <Route path="/events/:eventId" element={<EventDetailPage />} />
          <Route path="/cameras" element={<CamerasPage />} />
          <Route path="/cameras/:cameraId" element={<CameraDetailPage />} />
          <Route path="/cameras/:cameraId/calibrate" element={<CalibratePage />} />
          <Route path="/objects" element={<ObjectsPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
        </Routes>
      </Layout>
    </RequireAuth>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/*" element={<ProtectedApp />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
