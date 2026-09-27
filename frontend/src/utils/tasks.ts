// Правила отображения задач: подпись срока и группы на главном экране.
import type { Task, TaskStatus } from "../api/types";
import { addDays, dayMonth, diffDays, parseISO, today } from "./dates";

/** «был 20 июля» · «сегодня» · «до 27 июля» · «28 июля» — как в карточках макета. */
export function dueLabel(task: Task, now = today()): string {
  const due = parseISO(task.due);
  if (task.status === "done") return dayMonth(due);
  if (task.status === "overdue") return `был ${dayMonth(due)}`;
  if (diffDays(due, now) === 0) return "сегодня";
  if (task.status === "soon") return `до ${dayMonth(due)}`;
  return dayMonth(due);
}

const ORDER: Record<TaskStatus, number> = { overdue: 0, soon: 1, planned: 2, done: 3 };

export function byDue(a: Task, b: Task): number {
  return a.due.localeCompare(b.due) || ORDER[a.status] - ORDER[b.status];
}

/** Главный экран: «Сегодня» — просроченное и срок сегодня, «На неделе» — ближайшие 7 дней. */
export function dashboardGroups(tasks: Task[], now = today()) {
  const open = tasks.filter((t) => t.status !== "done").sort(byDue);
  const weekEnd = addDays(now, 7);
  return {
    today: open.filter((t) => t.status === "overdue" || diffDays(parseISO(t.due), now) <= 0),
    week: open.filter((t) => {
      const d = parseISO(t.due);
      return t.status !== "overdue" && diffDays(d, now) > 0 && d <= weekEnd;
    }),
  };
}

/** Точки дня в календаре: по одной на каждый статус, в порядке важности. */
export function dayDots(tasks: Task[]): TaskStatus[] {
  const set = new Set(tasks.map((t) => t.status));
  return (["overdue", "soon", "planned", "done"] as TaskStatus[]).filter((st) => set.has(st));
}
