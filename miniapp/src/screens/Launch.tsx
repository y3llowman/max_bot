import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { startParam } from "../max/bridge";
import { useSession } from "../session";
import { Splash } from "./Splash";

export function deepLinkTarget(p = startParam()): string {
  if (!p) return "/tasks";
  const task = /^task_([A-Za-z0-9_-]+)$/.exec(p);
  if (task) return `/task/${task[1]}`;
  if (p === "profile_edit") return "/profile/edit";
  if (p === "calendar" || p === "notifications" || p === "profile" || p === "feed") return `/${p}`;
  return "/tasks";
}

export function Launch() {
  const { status, reload } = useSession();
  const navigate = useNavigate();

  useEffect(() => {
    if (status === "ready") navigate(deepLinkTarget(), { replace: true });
    if (status === "none") navigate("/connect", { replace: true });
  }, [status, navigate]);

  return <Splash error={status === "error" ? "network" : status === "unauthorized" ? "unauthorized" : undefined} onRetry={reload} />;
}
