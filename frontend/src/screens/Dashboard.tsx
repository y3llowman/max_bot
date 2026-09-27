import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, cachedDashboard } from "../api/client";
import type { DashboardData } from "../api/types";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Chip } from "../components/Chip";
import { ContextBar } from "../components/ContextBar";
import { Icon } from "../components/Icon";
import { APP_NAME, Screen } from "../components/Screen";
import { SectionHeader } from "../components/SectionHeader";
import { CardSkeleton, Skeleton } from "../components/Skeleton";
import { NextDuePill, StateView } from "../components/StateView";
import { StatusTiles, StatusTilesSkeleton } from "../components/StatusTiles";
import { TaskCard } from "../components/TaskCard";
import { dateTime, dayMonth, diffDays, parseISO, today } from "../utils/dates";
import { dashboardGroups } from "../utils/tasks";
import { useAsync } from "../utils/useAsync";
import { openChat } from "../max/bridge";
import { useSession } from "../session";
import s from "./Dashboard.module.css";

/** 03 · Дашборд и состояния S1 (загрузка), S2 (пусто), S3 (ошибка). */
export function Dashboard() {
  const { data, error, loading, reload } = useAsync(() => api.dashboard(), []);
  const [saved, setSaved] = useState<DashboardData | null>(null);
  const view = saved ?? data;

  let body: ReactNode = null;
  if (loading && !saved) body = <DashboardSkeleton />;
  else if (error && !saved) body = <DashboardError onRetry={reload} onShowSaved={setSaved} />;
  else if (view) body = <DashboardContent data={view} stale={!!saved} />;

  return (
    <Screen title={APP_NAME}>
      <ContextBar unread={view?.unread} />
      {body}
    </Screen>
  );
}

function DashboardContent({ data, stale }: { data: DashboardData; stale: boolean }) {
  const navigate = useNavigate();
  const { company } = useSession();
  const groups = dashboardGroups(data.tasks);

  return (
    <>
      {company?.needsAnswers && (
        <Alert tone="info" title="Ответьте на 2 вопроса в чате" action={{ label: "Открыть чат", onClick: openChat }}>
          Режима налогообложения и численности нет в открытых реестрах. Без них часть обязанностей не видна.
        </Alert>
      )}
      {stale && data.savedAt && (
        <div>
          <Chip tone="neutral">{`Сохранено ${dateTime(data.savedAt)}`}</Chip>
        </div>
      )}
      <StatusTiles counters={data.counters} />
      {groups.today.length + groups.week.length === 0 ? (
        <DashboardEmpty data={data} onCalendar={() => navigate("/calendar")} />
      ) : (
        <>
          {groups.today.length > 0 && <SectionHeader title="Сегодня" count={groups.today.length} />}
          {groups.today.map((t) => (
            <TaskCard key={t.id} task={t} />
          ))}
          {groups.week.length > 0 && <SectionHeader title="На неделе" count={groups.week.length} />}
          {groups.week.map((t) => (
            <TaskCard key={t.id} task={t} />
          ))}
        </>
      )}
    </>
  );
}

/** S2. «На 30 дней всё спокойно» — только когда ближайший срок дальше 30 дней. */
function DashboardEmpty({ data, onCalendar }: { data: DashboardData; onCalendar: () => void }) {
  const next = data.nextDue ? parseISO(data.nextDue) : null;
  const calm30 = !next || diffDays(next, today()) > 30;
  const allDone = data.tasks.length === 0;
  return (
    <StateView
      tone="success"
      icon="calendar-check"
      title={calm30 ? "На 30 дней всё спокойно" : "На неделе всё спокойно"}
      text={
        allDone
          ? "Все обязанности выполнены. Напомним в чате MAX, когда появится новый срок."
          : "Ближайшие сроки — позже. Напомним в чате MAX заранее."
      }
      extra={next && <NextDuePill>{`Ближайший срок — ${dayMonth(next)}`}</NextDuePill>}
      actions={
        <Button size="m" variant="secondary" onClick={onCalendar}>
          Открыть календарь
        </Button>
      }
    />
  );
}

/** S3. По заметке дизайнера ошибка объясняет причину и даёт выход: повтор или сохранённые данные. */
function DashboardError({ onRetry, onShowSaved }: { onRetry: () => void; onShowSaved: (d: DashboardData) => void }) {
  const cached = cachedDashboard();
  return (
    <StateView
      tone="danger"
      icon="cloud-off"
      title="Не удалось обновить данные"
      text={
        cached
          ? "Сервис ФНС сейчас не отвечает. Ваши сроки не потерялись — можно открыть последнюю сохранённую версию."
          : "Сервис ФНС сейчас не отвечает. Попробуйте ещё раз через минуту."
      }
      extra={cached?.savedAt && <Chip tone="neutral">{`Сохранено ${dateTime(cached.savedAt)}`}</Chip>}
      actions={
        <>
          <Button size="m" onClick={onRetry}>
            Повторить
          </Button>
          {cached && (
            <Button size="m" variant="ghost" onClick={() => onShowSaved(cached)}>
              Показать сохранённые
            </Button>
          )}
        </>
      }
    />
  );
}

/** S1. Загрузка повторяет раскладку экрана. */
function DashboardSkeleton() {
  return (
    <>
      <StatusTilesSkeleton />
      <Skeleton width={96} height={16} />
      <CardSkeleton />
      <CardSkeleton />
      <Skeleton width={120} height={16} />
      <CardSkeleton />
      <p className={`t-note ${s.hint}`} role="status">
        <Icon name="refresh" size={16} className={s.spin} />
        Обновляем данные из ФНС…
      </p>
    </>
  );
}
