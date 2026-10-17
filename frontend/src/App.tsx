import type { ReactNode } from "react";
import { AppShell } from "./components/AppShell";
import { Loading } from "./components/ui";
import { useAuth } from "./lib/auth";
import { Redirect, Routes, useLocation } from "./lib/router";
import type { Role } from "./lib/types";
import AdminAudit from "./pages/admin/AdminAudit";
import AdminModels from "./pages/admin/AdminModels";
import AdminReference from "./pages/admin/AdminReference";
import AdminUsers from "./pages/admin/AdminUsers";
import BatchDetail from "./pages/BatchDetail";
import Batches from "./pages/Batches";
import BuyerDeliveries from "./pages/buyer/BuyerDeliveries";
import BuyerDemands from "./pages/buyer/BuyerDemands";
import CycleDetail from "./pages/CycleDetail";
import Dashboard from "./pages/Dashboard";
import FarmDetail from "./pages/FarmDetail";
import Farms from "./pages/Farms";
import Harvest from "./pages/Harvest";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import Notifications from "./pages/Notifications";
import ObservationDetail from "./pages/ObservationDetail";
import Observations from "./pages/Observations";
import Pollination from "./pages/Pollination";
import ProviderBookings from "./pages/provider/ProviderBookings";
import ProviderProfile from "./pages/provider/ProviderProfile";
import ReviewQueue from "./pages/reviewer/ReviewQueue";
import Settings from "./pages/Settings";

function Protected({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <div className="mx-auto max-w-md p-10"><Loading /></div>;
  if (!user) return <Redirect to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} />;
  if (roles && !roles.includes(user.role)) {
    return (
      <AppShell>
        <NotFound inApp message="This area isn't available for your role." />
      </AppShell>
    );
  }
  return <AppShell>{children}</AppShell>;
}

const F: Role[] = ["farmer"];

export default function App() {
  return (
    <Routes
      routes={[
        { path: "/", element: <Landing /> },
        { path: "/login", element: <Login /> },
        { path: "/app", element: <Protected><Dashboard /></Protected> },
        { path: "/app/farms", element: <Protected roles={F}><Farms /></Protected> },
        { path: "/app/farms/:farmId", element: <Protected roles={F}><FarmDetail /></Protected> },
        { path: "/app/cycles/:cycleId", element: <Protected roles={["farmer", "admin"]}><CycleDetail /></Protected> },
        { path: "/app/observations", element: <Protected roles={["farmer", "reviewer", "admin"]}><Observations /></Protected> },
        { path: "/app/observations/:obsId", element: <Protected roles={["farmer", "reviewer", "admin"]}><ObservationDetail /></Protected> },
        { path: "/app/harvest", element: <Protected roles={F}><Harvest /></Protected> },
        { path: "/app/pollination", element: <Protected roles={F}><Pollination /></Protected> },
        { path: "/app/batches", element: <Protected roles={F}><Batches /></Protected> },
        { path: "/app/batches/:batchId", element: <Protected roles={F}><BatchDetail /></Protected> },
        { path: "/app/provider/bookings", element: <Protected roles={["provider"]}><ProviderBookings /></Protected> },
        { path: "/app/provider/profile", element: <Protected roles={["provider"]}><ProviderProfile /></Protected> },
        { path: "/app/buyer/demands", element: <Protected roles={["buyer"]}><BuyerDemands /></Protected> },
        { path: "/app/buyer/deliveries", element: <Protected roles={["buyer"]}><BuyerDeliveries /></Protected> },
        { path: "/app/review", element: <Protected roles={["reviewer"]}><ReviewQueue /></Protected> },
        { path: "/app/admin/users", element: <Protected roles={["admin"]}><AdminUsers /></Protected> },
        { path: "/app/admin/reference", element: <Protected roles={["admin"]}><AdminReference /></Protected> },
        { path: "/app/admin/models", element: <Protected roles={["admin"]}><AdminModels /></Protected> },
        { path: "/app/admin/audit", element: <Protected roles={["admin"]}><AdminAudit /></Protected> },
        { path: "/app/settings", element: <Protected><Settings /></Protected> },
        { path: "/app/notifications", element: <Protected><Notifications /></Protected> },
      ]}
      fallback={<NotFound />}
    />
  );
}
