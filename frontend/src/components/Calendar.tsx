import type { Task, TaskStatus } from "../api/types";
import { addDays, sameDay, toISO, weekdayShort, WEEKDAYS } from "../utils/dates";
import { dayDots } from "../utils/tasks";
import { IconButton } from "./Button";
import s from "./Calendar.module.css";

interface HeadProps {
  title: string;
  prevLabel: string;
  nextLabel: string;
  onPrev: () => void;
  onNext: () => void;
}

function Head({ title, prevLabel, nextLabel, onPrev, onNext }: HeadProps) {
  return (
    <div className={s.head}>
      <IconButton icon="chevron-left" label={prevLabel} onClick={onPrev} />
      <span className="t-title" aria-live="polite">
        {title}
      </span>
      <IconButton icon="chevron-right" label={nextLabel} onClick={onNext} />
    </div>
  );
}

function Dots({ statuses }: { statuses: TaskStatus[] }) {
  return (
    <span className={s.dots} aria-hidden="true">
      {statuses.map((st) => (
        <span key={st} className={`${s.dot} ${s[st]}`} />
      ))}
    </span>
  );
}

function tasksByDay(tasks: Task[]) {
  const map = new Map<string, Task[]>();
  for (const t of tasks) map.set(t.due, [...(map.get(t.due) ?? []), t]);
  return map;
}

interface WeekProps {
  monday: Date;
  today: Date;
  selected: Date | null;
  tasks: Task[];
  title: string;
  onSelect: (d: Date) => void;
  onShift: (weeks: number) => void;
}

/** Неделя (05, S6): 7 ячеек 46×68 с шагом 2; выбранный день — заливка, сегодня — обводка. */
export function WeekStrip({ monday, today, selected, tasks, title, onSelect, onShift }: WeekProps) {
  const byDay = tasksByDay(tasks);
  return (
    <div className={`${s.card} ${s.weekCard}`}>
      <Head title={title} prevLabel="Предыдущая неделя" nextLabel="Следующая неделя" onPrev={() => onShift(-1)} onNext={() => onShift(1)} />
      <div className={s.week} role="grid" aria-label="Дни недели">
        {Array.from({ length: 7 }, (_, i) => {
          const d = addDays(monday, i);
          const isSel = selected !== null && sameDay(d, selected);
          const isToday = sameDay(d, today);
          const dots = dayDots(byDay.get(toISO(d)) ?? []);
          return (
            <button
              key={i}
              type="button"
              role="gridcell"
              aria-selected={isSel}
              aria-current={isToday ? "date" : undefined}
              aria-label={`${weekdayShort(d)}, ${d.getDate()}${dots.length ? `, сроков: ${byDay.get(toISO(d))?.length}` : ""}`}
              className={`${s.weekDay} ${isSel ? s.selected : isToday ? s.today : ""}`}
              onClick={() => onSelect(d)}
            >
              <span className="t-note">{weekdayShort(d)}</span>
              <span className={`t-subheader ${s.num}`}>{d.getDate()}</span>
              <Dots statuses={dots} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

interface MonthProps {
  month: Date;
  today: Date;
  selected: Date;
  tasks: Task[];
  title: string;
  onSelect: (d: Date) => void;
  onShift: (months: number) => void;
}

/** Месяц (E2): сетка 7×N, ячейка 50×46; дни соседних месяцев приглушены. */
export function MonthGrid({ month, today, selected, tasks, title, onSelect, onShift }: MonthProps) {
  const byDay = tasksByDay(tasks);
  const first = monthGridStart(month);
  const weeks = monthWeeks(month);
  return (
    <div className={`${s.card} ${s.monthCard}`}>
      <Head title={title} prevLabel="Предыдущий месяц" nextLabel="Следующий месяц" onPrev={() => onShift(-1)} onNext={() => onShift(1)} />
      <div className={s.weekdays} aria-hidden="true">
        {WEEKDAYS.map((w) => (
          <span key={w} className="t-note-strong">
            {w}
          </span>
        ))}
      </div>
      <div className={s.grid} role="grid" aria-label={title}>
        {Array.from({ length: weeks * 7 }, (_, i) => {
          const d = addDays(first, i);
          const muted = d.getMonth() !== month.getMonth();
          const isSel = sameDay(d, selected);
          const isToday = sameDay(d, today);
          const dots = dayDots(byDay.get(toISO(d)) ?? []);
          return (
            <button
              key={i}
              type="button"
              role="gridcell"
              aria-selected={isSel}
              aria-current={isToday ? "date" : undefined}
              aria-label={`${d.getDate()}${dots.length ? `, сроков: ${byDay.get(toISO(d))?.length}` : ""}`}
              className={`${s.day} ${muted ? s.muted : ""} ${isSel ? s.selected : isToday ? s.today : ""}`}
              onClick={() => onSelect(d)}
            >
              <span className={isSel ? "t-body-strong" : "t-body"}>{d.getDate()}</span>
              <Dots statuses={dots} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Понедельник первой строки сетки месяца. */
export function monthGridStart(month: Date): Date {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  return addDays(first, -((first.getDay() + 6) % 7));
}

export function monthWeeks(month: Date): number {
  const start = monthGridStart(month);
  const last = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const days = Math.round((last.getTime() - start.getTime()) / 86_400_000) + 1;
  return Math.ceil(days / 7);
}
