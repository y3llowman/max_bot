import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { NotificationSettings, RemindMode } from "../api/types";
import { ActionBar } from "../components/ActionBar";
import { Button } from "../components/Button";
import { Radio, Toggle } from "../components/Controls";
import { ListCell, ListGroup } from "../components/List";
import { Screen } from "../components/Screen";
import { SectionHeader } from "../components/SectionHeader";
import { Skeleton } from "../components/Skeleton";
import { StateView } from "../components/StateView";
import { useToast } from "../components/Toast";
import { useAsync } from "../utils/useAsync";

const QUIET_RANGES = ["22:00–08:00", "23:00–07:00", "21:00–09:00", "00:00–08:00"];

const REMIND: { value: RemindMode; label: string }[] = [
  { value: "d30-7-1", label: "За 30, 7 и 1 день до срока" },
  { value: "d7-3-1", label: "За 7, 3 и 1 день до срока" },
  { value: "d3-0", label: "За 3 дня и в день срока" },
  { value: "d0", label: "Только в день срока" },
];

const range = (r: string) => r.replace("–", " – ");

/** 07 · Уведомления. */
export function Notifications() {
  const { data, error, loading, reload, setData } = useAsync(() => api.notifications(), []);
  const [draft, setDraft] = useState<NotificationSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  useEffect(() => {
    if (data) setDraft(data);
  }, [data]);

  const set = <K extends keyof NotificationSettings>(key: K, value: NotificationSettings[K]) =>
    setDraft((d) => (d ? { ...d, [key]: value } : d));

  const save = async () => {
    if (!draft || !data) return;
    const previous = data;
    setSaving(true);
    try {
      await api.saveNotifications(draft);
      setData(draft);
      toast({
        text: "Настройки сохранены",
        action: {
          label: "Отменить",
          onClick: () => {
            setDraft(previous);
            setData(previous);
            api.saveNotifications(previous).catch(() =>
              toast({ text: "Не получилось отменить — попробуйте ещё раз", icon: "alert-circle" }),
            );
          },
        },
      });
    } catch {
      toast({ text: "Не получилось сохранить — попробуйте ещё раз", icon: "alert-circle" });
    } finally {
      setSaving(false);
    }
  };

  if (error) {
    return (
      <Screen title="Уведомления" nav="back">
        <StateView
          tone="danger"
          icon="cloud-off"
          title="Не удалось загрузить настройки"
          text="Проверьте интернет и попробуйте ещё раз."
          actions={
            <Button size="m" onClick={reload}>
              Повторить
            </Button>
          }
        />
      </Screen>
    );
  }

  return (
    <Screen
      title="Уведомления"
      nav="back"
      gap={10}
      bottom={
        <ActionBar>
          <Button block onClick={save} disabled={!draft || saving}>
            Сохранить
          </Button>
        </ActionBar>
      }
    >
      {loading || !draft ? (
        <>
          <Skeleton width={140} height={16} />
          <Skeleton height={192} radius={16} />
          <Skeleton width={110} height={16} />
          <Skeleton height={107} radius={16} />
        </>
      ) : (
        <>
          <SectionHeader title="Куда присылать" />
          <ListGroup>
            <ListCell
              title="Чат с ботом в MAX"
              caption="Основной канал"
              role="switch"
              checked={draft.chat}
              onClick={() => set("chat", !draft.chat)}
              trail={<Toggle checked={draft.chat} />}
            />
            <ListCell
              title="Push-уведомления"
              role="switch"
              checked={draft.push}
              onClick={() => set("push", !draft.push)}
              trail={<Toggle checked={draft.push} />}
            />
            <ListCell
              title="Электронная почта"
              caption={draft.emailAddress}
              role="switch"
              checked={draft.email}
              onClick={() => set("email", !draft.email)}
              trail={<Toggle checked={draft.email} />}
            />
          </ListGroup>

          <SectionHeader title="Тихие часы" />
          <ListGroup>
            <ListCell
              title="Не беспокоить ночью"
              role="switch"
              checked={draft.quiet}
              onClick={() => set("quiet", !draft.quiet)}
              trail={<Toggle checked={draft.quiet} />}
            />
            <ListCell
              title="Время"
              value={range(draft.quietRange)}
              chevron
              disabled={!draft.quiet}
              select={{
                value: draft.quietRange,
                options: QUIET_RANGES.map((r) => ({ value: r, label: range(r) })),
                onChange: (v) => set("quietRange", v),
              }}
            />
          </ListGroup>

          <SectionHeader title="Когда напоминать" />
          <ListGroup label="Когда напоминать" radio>
            {REMIND.map((r) => (
              <ListCell
                key={r.value}
                title={r.label}
                role="radio"
                checked={draft.remind === r.value}
                onClick={() => set("remind", r.value)}
                lead={<Radio checked={draft.remind === r.value} />}
              />
            ))}
          </ListGroup>
        </>
      )}
    </Screen>
  );
}
