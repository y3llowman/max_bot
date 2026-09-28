import type { ReactNode } from "react";
import { Navigate, Outlet, RouterProvider, createHashRouter } from "react-router-dom";
import { TabBar } from "./components/TabBar";
import { ToastProvider } from "./components/Toast";
import { CalendarScreen } from "./screens/Calendar";
import { Connect } from "./screens/Connect";
import { Dashboard } from "./screens/Dashboard";
import { Launch } from "./screens/Launch";
import { Notifications } from "./screens/Notifications";
import { Profile } from "./screens/Profile";
import { Splash } from "./screens/Splash";
import { TaskScreen } from "./screens/Task";
import { SessionProvider, useSession } from "./session";

/** Экраны разделов и вложенные ждут компанию; без неё — на подключение. */
function RequireSession({ children }: { children: ReactNode }) {
  const { status, reload } = useSession();
  if (status === "loading") return <Splash />;
  if (status === "error") return <Splash error="network" onRetry={reload} />;
  if (status === "unauthorized") return <Splash error="unauthorized" />;
  if (status === "none") return <Navigate to="/connect" replace />;
  return children;
}

/** Верхний уровень: крестик в шапке MAX и таббар. */
function TabsLayout() {
  return (
    <RequireSession>
      <div className="layout">
        <Outlet />
        <TabBar />
      </div>
    </RequireSession>
  );
}

// Хеш-роутинг: статический хостинг не нужно настраивать на переадресацию путей.
const router = createHashRouter([
  { path: "/", element: <Launch /> },
  { path: "/connect", element: <Connect /> },
  {
    element: <TabsLayout />,
    children: [
      { path: "/tasks", element: <Dashboard /> },
      { path: "/calendar", element: <CalendarScreen /> },
      { path: "/profile", element: <Profile /> },
    ],
  },
  { path: "/task/:id", element: <RequireSession><TaskScreen /></RequireSession> },
  { path: "/notifications", element: <RequireSession><Notifications /></RequireSession> },
  { path: "*", element: <Navigate to="/" replace /> },
]);

export function App() {
  return (
    <SessionProvider>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </SessionProvider>
  );
}
