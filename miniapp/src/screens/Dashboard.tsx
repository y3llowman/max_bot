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
import { RadarScan } from "../components/RadarScan";
import { StatusTiles, StatusTilesSkeleton } from "../components/StatusTiles";
import { TaskCard } from "../components/TaskCard";
import { useToast } from "../components/Toast";
import { dateTime, dayMonth, diffDays, parseISO, today } from "../utils/dates";
import { dashboardGroups } from "../utils/tasks";
import { useAsync } from "../utils/useAsync";
import { useSession } from "../session";
import s from "./Dashboard.module.css";

export function Dashboard() {
  const { data, error, loading, reload } = useAsync(() => api.dashboard(), []);
  const [saved, setSaved] = useState<DashboardData | null>(null);
  const view = saved ?? data;

  let body: ReactNode = null;
  if (loading && !saved) body = <DashboardSkeleton />;
  else if (error && !saved) body = <DashboardError onRetry={reload} onShowSaved={setSaved} />;
  else if (view) body = <DashboardContent data={view} stale={!!saved} onScanned={reload} />;

  return (
    <Screen title={APP_NAME}>
      <ContextBar unread={view?.unread} />
      {body}
    </Screen>
  );
}

function DashboardContent({ data, stale, onScanned }: { data: DashboardData; stale: boolean; onScanned: () => void }) {
  const navigate = useNavigate();
  const { company, setCompany } = useSession();
  const toast = useToast();
  const [scanning, setScanning] = useState(false);
  const groups = dashboardGroups(data.tasks);

  const scan = async () => {
    setScanning(true);
    try {
      setCompany(await api.refreshCompany());
      onScanned();
      toast({ text: "Реестр МСП проверен, ЕГРЮЛ проверяем в фоне — находки придут в чат" });
    } catch {
      toast({ text: "ФНС не отвечает — попробуйте позже", icon: "alert-circle" });
    } finally {
      setScanning(false);
    }
  };

  return (
    <>
      {company?.needsAnswers && (
        <Alert tone="info" title="Укажите режим и численность" action={{ label: "Указать", onClick: () => navigate("/profile/edit") }}>
          Режима налогообложения, а иногда и численности, нет в открытых реестрах. Без них часть обязанностей не видна.
        </Alert>
      )}
      <RadarScan scanning={scanning} checkedAt={company?.source.updatedAt} onScan={scan} />
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
      {groups.listed.length > 0 && <SectionHeader title="Список дел" count={groups.listed.length} />}
      {groups.listed.map((t) => (
        <TaskCard key={t.id} task={t} />
      ))}
    </>
  );
}

function DashboardEmpty({ data, onCalendar }: { data: DashboardData; onCalendar: () => void }) {
  const next = data.nextDue ? parseISO(data.nextDue) : null;
  const calm30 = !next || diffDays(next, today()) > 30;
  const allDone = data.tasks.every((t) => !t.due);
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
