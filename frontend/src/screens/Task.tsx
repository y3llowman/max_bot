import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { TaskDetails } from "../api/types";
import { Accordion } from "../components/Accordion";
import { ActionBar, ActionRow } from "../components/ActionBar";
import { Button } from "../components/Button";
import { Chip, StatusChip } from "../components/Chip";
import { Icon } from "../components/Icon";
import { Screen } from "../components/Screen";
import { SectionHeader } from "../components/SectionHeader";
import { Skeleton } from "../components/Skeleton";
import { StateView } from "../components/StateView";
import { TaskCard } from "../components/TaskCard";
import { useToast } from "../components/Toast";
import { parseISO, timeLeft } from "../utils/dates";
import { useAsync } from "../utils/useAsync";
import { haptic, openChat } from "../max/bridge";
import s from "./Task.module.css";

const TITLE = "Задача";

/** 04 · Детали задачи, E5 · Результат действия, E4 · Задача выполнена, S4 · загрузка, S5 · ошибка. */
export function TaskScreen() {
  const { id = "" } = useParams();
  const { data: task, error, loading, reload, setData } = useAsync(() => api.task(id), [id]);

  if (loading) return <TaskLoading />;
  if (error || !task) return <TaskError error={error} onRetry={reload} />;
  if (task.status === "done") return <TaskDone task={task} />;
  return <TaskOpen task={task} onDone={() => setData({ ...task, status: "done" })} />;
}

function TaskOpen({ task, onDone }: { task: TaskDetails; onDone: () => void }) {
  const [submitted, setSubmitted] = useState(false);
  const [generating, setGenerating] = useState(false);
  const toast = useToast();

  useEffect(() => setSubmitted(false), [task.id]);

  // По заметке дизайнера: после «Уже подано» — уведомление о результате с отменой; тупиков нет.
  // Не отменили за 5 секунд — задача выполнена, показываем E4.
  const markSubmitted = async () => {
    setSubmitted(true);
    try {
      await api.markSubmitted(task.id);
    } catch {
      setSubmitted(false);
      toast({ text: "Не получилось отметить — попробуйте ещё раз", icon: "alert-circle" });
      return;
    }
    haptic.success();
    toast({
      text: task.submittedNote ?? "Отмечено как выполненное",
      action: {
        label: "Отменить",
        onClick: () => {
          setSubmitted(false);
          api.undoSubmitted(task.id).catch(() =>
            toast({ text: "Не получилось отменить — попробуйте ещё раз", icon: "alert-circle" }),
          );
        },
      },
      onTimeout: onDone,
    });
  };

  const generate = async () => {
    setGenerating(true);
    try {
      await api.generateDocument(task.id);
      haptic.success();
      toast({ text: "Документ готов — отправили в чат с ботом", action: { label: "Открыть", onClick: openChat } });
    } catch {
      toast({ text: "Не получилось сформировать документ — попробуйте ещё раз", icon: "alert-circle" });
    } finally {
      setGenerating(false);
    }
  };

  return (
    <Screen
      title={TITLE}
      nav="back"
      gap={0}
      bottom={
        <ActionBar>
          <ActionRow>
            <Button variant="outline" disabled={submitted} onClick={markSubmitted}>
              Выполнено
            </Button>
            {task.document && (
              <Button disabled={generating} onClick={generate}>
                Подготовить документ
              </Button>
            )}
          </ActionRow>
        </ActionBar>
      }
    >
      <div className={s.status}>
        <StatusChip status={task.status} />
        {task.periodicity && <Chip tone="neutral">{task.periodicity}</Chip>}
        <span className="t-note-strong c-secondary">{timeLeft(parseISO(task.due))}</span>
      </div>
      <div className={s.title}>
        <span className={s.icon}>
          <Icon name="file" size={22} />
        </span>
        <h1 className="t-subheader">{task.heading}</h1>
      </div>
      {/* «Почему я это вижу» раскрыт сразу: доверие к ленте держится на объяснении */}
      <Accordion sections={task.sections} defaultOpen={["why", "risks"]} />
    </Screen>
  );
}

/** E4. Главное действие после выполнения — вернуться в чат MAX. */
function TaskDone({ task }: { task: TaskDetails }) {
  const navigate = useNavigate();
  return (
    <Screen
      title={TITLE}
      nav="back"
      gap={0}
      bottom={
        <ActionBar>
          <Button block onClick={openChat}>
            Вернуться в чат MAX
          </Button>
          <Button block variant="ghost" onClick={() => navigate("/tasks")}>
            К списку обязанностей
          </Button>
        </ActionBar>
      }
    >
      <div className={s.done}>
        <div className={s.ring} aria-hidden="true">
          <Icon name="check-circle" size={44} />
        </div>
        <h1 className="t-header">{task.done?.title ?? "Готово"}</h1>
        {task.done?.text && <p className={`t-detail ${s.doneText}`}>{task.done.text}</p>}
      </div>
      {task.next && (
        <div className={s.next}>
          <SectionHeader title="Следующий срок" />
          <TaskCard task={task.next} />
        </div>
      )}
    </Screen>
  );
}

function TaskError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const navigate = useNavigate();
  const notFound = error instanceof ApiError && error.code === "not_found";
  return (
    <Screen title={TITLE} nav="back">
      {notFound ? (
        <StateView
          tone="primary"
          icon="inbox"
          title="Задача не найдена"
          text="Возможно, её уже закрыли или ссылка устарела."
          actions={
            <Button size="m" variant="secondary" onClick={() => navigate("/tasks", { replace: true })}>
              К списку обязанностей
            </Button>
          }
        />
      ) : (
        <StateView
          tone="warning"
          icon="alert-triangle"
          title="Не получилось открыть задачу"
          text="Похоже, пропал интернет. Проверьте подключение — или вернитесь в чат: бот пришлёт напоминание ещё раз."
          actions={
            <>
              <Button size="m" onClick={onRetry}>
                Повторить
              </Button>
              <Button size="m" variant="ghost" onClick={openChat}>
                Вернуться в чат MAX
              </Button>
            </>
          }
        />
      )}
    </Screen>
  );
}

/** S4: раскладка экрана задачи, кнопки неактивны. */
function TaskLoading() {
  return (
    <Screen
      title={TITLE}
      nav="back"
      gap={12}
      bottom={
        <ActionBar>
          <ActionRow>
            <Button variant="outline" disabled>
              Выполнено
            </Button>
            <Button disabled>Подготовить документ</Button>
          </ActionRow>
        </ActionBar>
      }
    >
      <div aria-hidden="true" className={s.skeleton}>
        <Skeleton width={96} height={24} />
        <div className={s.skeletonHead}>
          <Skeleton width={44} height={44} radius={12} />
          <div className={s.skeletonLines}>
            <Skeleton height={18} />
            <Skeleton width={160} height={18} />
          </div>
        </div>
        <Skeleton height={14} radius={7} />
        <div className={s.skeletonCard}>
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className={s.skeletonRow}>
              <Skeleton width={40} height={40} radius={12} />
              <div className={s.skeletonLines}>
                <Skeleton height={14} radius={7} />
                <Skeleton width={120} height={12} radius={6} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </Screen>
  );
}
