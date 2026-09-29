import type { ReactNode } from "react";
import { Navigate, Outlet, RouterProvider, createHashRouter } from "react-router-dom";
import { Button } from "./components/Button";
import { APP_NAME, Screen } from "./components/Screen";
import { StateView } from "./components/StateView";
import { TabBar } from "./components/TabBar";
import { ToastProvider } from "./components/Toast";
import { CalendarScreen } from "./screens/Calendar";
import { Connect } from "./screens/Connect";
import { Dashboard } from "./screens/Dashboard";
import { Feed } from "./screens/Feed";
import { Launch, deepLinkTarget } from "./screens/Launch";
import { Notifications } from "./screens/Notifications";
import { Profile } from "./screens/Profile";
import { ProfileEdit } from "./screens/ProfileEdit";
import { Splash } from "./screens/Splash";
import { TaskScreen } from "./screens/Task";
import { SessionProvider, useSession } from "./session";
import { onRelaunch } from "./max/bridge";

function RequireSession({ children }: { children: ReactNode }) {
  const { status, reload } = useSession();
  if (status === "loading") return <Splash />;
  if (status === "error") return <Splash error="network" onRetry={reload} />;
  if (status === "unauthorized") return <Splash error="unauthorized" />;
  if (status === "none") return <Navigate to="/connect" replace />;
  return children;
}

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

function RouteError() {
  return (
    <Screen title={APP_NAME}>
      <StateView
        tone="danger"
        icon="alert-circle"
        title="Что-то пошло не так"
        text="Экран не открылся. Перезапустите приложение — данные компании и задачи сохранены."
        actions={
          <Button size="m" onClick={() => window.location.replace(window.location.pathname)}>
            Перезапустить
          </Button>
        }
      />
    </Screen>
  );
}

const router = createHashRouter([
  {
    errorElement: <RouteError />,
    children: [
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
      { path: "/feed", element: <RequireSession><Feed /></RequireSession> },
      { path: "/profile/edit", element: <RequireSession><ProfileEdit /></RequireSession> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);

onRelaunch((param) => router.navigate(deepLinkTarget(param), { replace: true }));

export function App() {
  return (
    <SessionProvider>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </SessionProvider>
  );
}
