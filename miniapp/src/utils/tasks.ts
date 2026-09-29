import type { Task, TaskStatus } from "../api/types";
import { dayMonth, diffDays, parseISO, today } from "./dates";

export function dueLabel(task: Task, now = today()): string {
  if (!task.due) return task.status === "done" ? "" : "без срока";
  const due = parseISO(task.due);
  if (task.status === "done") return dayMonth(due);
  if (task.status === "overdue") return `был ${dayMonth(due)}`;
  if (diffDays(due, now) === 0) return "сегодня";
  if (task.status === "soon") return `до ${dayMonth(due)}`;
  return dayMonth(due);
}

const ORDER: Record<TaskStatus, number> = { overdue: 0, soon: 1, planned: 2, done: 3 };

export function byDue(a: Task, b: Task): number {
  return (a.due ?? "9999").localeCompare(b.due ?? "9999") || ORDER[a.status] - ORDER[b.status];
}

export function dashboardGroup(task: Task, now = today()): "today" | "week" | null {
  if (!task.due) return null;
  if (task.status === "overdue") return "today";
  const days = diffDays(parseISO(task.due), now);
  if (days <= 0) return "today";
  return days <= 7 ? "week" : null;
}

export function dashboardGroups(tasks: Task[], now = today()) {
  const open = tasks.filter((t) => t.status !== "done").sort(byDue);
  return {
    today: open.filter((t) => dashboardGroup(t, now) === "today"),
    week: open.filter((t) => dashboardGroup(t, now) === "week"),
    listed: open.filter((t) => !dashboardGroup(t, now) && (t.listed || !t.due)),
  };
}

export function dayDots(tasks: Task[]): TaskStatus[] {
  const set = new Set(tasks.map((t) => t.status));
  return (["overdue", "soon", "planned", "done"] as TaskStatus[]).filter((st) => set.has(st));
}
