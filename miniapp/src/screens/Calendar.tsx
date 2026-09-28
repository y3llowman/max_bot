import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { Task } from "../api/types";
import { Button } from "../components/Button";
import { MonthGrid, WeekStrip, monthGridStart, monthWeeks } from "../components/Calendar";
import { Chip } from "../components/Chip";
import { Screen } from "../components/Screen";
import { SectionHeader } from "../components/SectionHeader";
import { Segmented } from "../components/Segmented";
import { CardSkeleton } from "../components/Skeleton";
import { StateView } from "../components/StateView";
import { TaskCard } from "../components/TaskCard";
import {
  addDays, addMonths, dayMonth, dayTitle, monthTitle, parseISO, sameDay, startOfMonth, startOfWeek, toISO, today, weekRange,
} from "../utils/dates";
import { byDue } from "../utils/tasks";
import { useAsync } from "../utils/useAsync";
import s from "./Calendar.module.css";

type View = "month" | "week" | "list";

const VIEWS: { value: View; label: string }[] = [
  { value: "month", label: "Месяц" },
  { value: "week", label: "Неделя" },
  { value: "list", label: "Список" },
];

export function CalendarScreen() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("view");
  const view: View = raw === "month" || raw === "list" ? raw : "week";

  return (
    <Screen title="Календарь">
      <Segmented label="Вид календаря" options={VIEWS} value={view} onChange={(v) => setParams({ view: v }, { replace: true })} />
      {view === "week" && <WeekView />}
      {view === "month" && <MonthView />}
      {view === "list" && <ListView />}
    </Screen>
  );
}

/** 05 · Неделя и S6 · Неделя пусто. Под неделей — дни со сроками; тап по дню прокручивает к нему. */
function WeekView() {
  const now = today();
  const [monday, setMonday] = useState(() => startOfWeek(now));
  const [selected, setSelected] = useState<Date | null>(now);
  const from = toISO(monday);
  const to = toISO(addDays(monday, 6));
  const { data, error, loading, reload } = useAsync(() => api.calendar(from, to), [from]);

  const shift = (weeks: number) => {
    const next = addDays(monday, weeks * 7);
    setMonday(next);
    setSelected(sameDay(startOfWeek(now), next) ? now : null);
  };

  const select = (d: Date) => {
    setSelected(d);
    document.getElementById(`day-${toISO(d)}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const tasks = data ?? [];
  return (
    <>
      <WeekStrip monday={monday} today={now} selected={selected} tasks={tasks} title={weekRange(monday)} onSelect={select} onShift={shift} />
      {loading ? (
        <>
          <CardSkeleton />
          <CardSkeleton />
        </>
      ) : error ? (
        <CalendarError onRetry={reload} />
      ) : tasks.length === 0 ? (
        <WeekEmpty weekEnd={to} onNext={() => shift(1)} />
      ) : (
        groupByDay(tasks).map(([iso, list]) => <DayGroup key={iso} date={parseISO(iso)} tasks={list} now={now} />)
      )}
    </>
  );
}

function DayGroup({ date, tasks, now }: { date: Date; tasks: Task[]; now: Date }) {
  const isToday = sameDay(date, now);
  return (
    <section className={s.day} id={`day-${toISO(date)}`}>
      <div className={s.dayHead}>
        <h3 className={`t-label-strong ${isToday ? "c-accent" : "c-secondary"}`}>{dayTitle(date)}</h3>
        {isToday && <Chip tone="primary">Сегодня</Chip>}
      </div>
      {tasks.map((t) => (
        <TaskCard key={t.id} task={t} />
      ))}
    </section>
  );
}

/** S6: пустая неделя подсказывает следующий срок и ведёт на следующую неделю. */
function WeekEmpty({ weekEnd, onNext }: { weekEnd: string; onNext: () => void }) {
  const from = toISO(addDays(parseISO(weekEnd), 1));
  const until = toISO(addDays(parseISO(weekEnd), 120));
  const { data } = useAsync(() => api.calendar(from, until), [from]);
  const next = data?.filter((t) => t.status !== "done").sort(byDue)[0];
  return (
    <StateView
      tone="primary"
      icon="calendar-check"
      title="На этой неделе сроков нет"
      text={next ? `Можно выдохнуть. Следующий срок — ${dayMonth(parseISO(next.due))}.` : "Можно выдохнуть."}
      actions={
        <Button size="m" variant="secondary" onClick={onNext}>
          Следующая неделя
        </Button>
      }
    />
  );
}

/** E2 · Месяц: под сеткой — сроки выбранного дня. */
function MonthView() {
  const now = today();
  const [month, setMonth] = useState(() => startOfMonth(now));
  const [selected, setSelected] = useState(now);
  const start = monthGridStart(month);
  const end = addDays(start, monthWeeks(month) * 7 - 1);
  const { data, error, loading, reload } = useAsync(() => api.calendar(toISO(start), toISO(end)), [toISO(start)]);

  const shift = (months: number) => {
    const next = addMonths(month, months);
    setMonth(next);
    const current = next.getFullYear() === now.getFullYear() && next.getMonth() === now.getMonth();
    setSelected(current ? now : next);
  };

  const select = (d: Date) => {
    setSelected(d);
    if (d.getMonth() !== month.getMonth()) setMonth(startOfMonth(d));
  };

  const dayTasks = (data ?? []).filter((t) => t.due === toISO(selected)).sort(byDue);
  const isToday = sameDay(selected, now);

  return (
    <>
      <MonthGrid month={month} today={now} selected={selected} tasks={data ?? []} title={monthTitle(month)} onSelect={select} onShift={shift} />
      {error ? (
        <CalendarError onRetry={reload} />
      ) : (
        <>
          <SectionHeader title={`${dayTitle(selected)}${isToday ? " · сегодня" : ""}`} count={loading ? undefined : dayTasks.length} />
          {loading ? (
            <CardSkeleton />
          ) : dayTasks.length > 0 ? (
            dayTasks.map((t) => <TaskCard key={t.id} task={t} />)
          ) : (
            <p className="t-detail c-secondary">В этот день сроков нет</p>
          )}
        </>
      )}
    </>
  );
}

/** E3 · Список: открытые задачи по неделям. Просроченное — в «Этой неделе», его нужно сделать сейчас. */
function ListView() {
  const now = today();
  const from = toISO(addDays(now, -90));
  const to = toISO(addDays(now, 180));
  const { data, error, loading, reload } = useAsync(() => api.calendar(from, to), [from]);

  if (loading) {
    return (
      <>
        <CardSkeleton />
        <CardSkeleton />
        <CardSkeleton />
      </>
    );
  }
  if (error) return <CalendarError onRetry={reload} />;

  const open = (data ?? []).filter((t) => t.status !== "done").sort(byDue);
  const nextMonday = addDays(startOfWeek(now), 7);
  const afterNext = addDays(nextMonday, 7);
  const groups: [string, Task[]][] = [
    ["Эта неделя", open.filter((t) => parseISO(t.due) < nextMonday)],
    ["Следующая неделя", open.filter((t) => parseISO(t.due) >= nextMonday && parseISO(t.due) < afterNext)],
    ["Позже", open.filter((t) => parseISO(t.due) >= afterNext)],
  ];
  const visible = groups.filter(([, list]) => list.length > 0);

  if (visible.length === 0) {
    return (
      <StateView
        tone="primary"
        icon="calendar-check"
        title="Открытых сроков нет"
        text="Можно выдохнуть. Напомним в чате MAX, когда появится новый срок."
      />
    );
  }

  return (
    <>
      {visible.map(([title, list]) => (
        <section key={title} className={s.group}>
          <SectionHeader title={title} count={list.length} />
          {list.map((t) => (
            <TaskCard key={t.id} task={t} />
          ))}
        </section>
      ))}
    </>
  );
}

function CalendarError({ onRetry }: { onRetry: () => void }) {
  return (
    <StateView
      tone="danger"
      icon="cloud-off"
      title="Не удалось загрузить календарь"
      text="Проверьте интернет и попробуйте ещё раз."
      actions={
        <Button size="m" onClick={onRetry}>
          Повторить
        </Button>
      }
    />
  );
}

function groupByDay(tasks: Task[]): [string, Task[]][] {
  const map = new Map<string, Task[]>();
  for (const t of [...tasks].sort(byDue)) map.set(t.due, [...(map.get(t.due) ?? []), t]);
  return [...map.entries()];
}
