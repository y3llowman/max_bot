import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { startParam } from "../max/bridge";
import { useSession } from "../session";
import { Splash } from "./Splash";

/** Куда ведёт диплинк https://max.ru/<бот>?startapp=<payload>.
 *  task_<id> — экран события (кнопка «Открыть» под пушем), profile_edit — «Данные компании»
 *  (карточка «Нашли вашу компанию» и /profile), feed, calendar, notifications, profile — разделы. */
function deepLinkTarget(): string {
  const p = startParam();
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
