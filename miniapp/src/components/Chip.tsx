import type { TaskStatus } from "../api/types";
import s from "./Chip.module.css";

export type ChipTone = "danger" | "warning" | "success" | "info" | "primary" | "neutral";

export function Chip({ tone, children }: { tone: ChipTone; children: string }) {
  return (
    <span className={`${s.chip} ${s[tone]}`}>
      <span className={s.dot} aria-hidden="true" />
      {children}
    </span>
  );
}

export const STATUS: Record<TaskStatus, { tone: ChipTone; label: string }> = {
  overdue: { tone: "danger", label: "Просрочено" },
  soon: { tone: "warning", label: "Скоро" },
  planned: { tone: "info", label: "Запланировано" },
  done: { tone: "success", label: "Выполнено" },
};

export function StatusChip({ status }: { status: TaskStatus }) {
  return <Chip tone={STATUS[status].tone}>{STATUS[status].label}</Chip>;
}
