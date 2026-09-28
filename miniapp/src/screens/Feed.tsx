import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { FeedItem } from "../api/types";
import { Button } from "../components/Button";
import { ListCell, ListGroup } from "../components/List";
import { Screen } from "../components/Screen";
import { Skeleton } from "../components/Skeleton";
import { StateView } from "../components/StateView";
import { dateTime, dayMonth, diffDays, parseISO, today } from "../utils/dates";
import { useAsync } from "../utils/useAsync";

const ICON: Record<FeedItem["severity"], string> = { critical: "🔴", warning: "🟠", info: "🔵" };

/** Справа: чем всё кончилось — «выполнено», «не актуально», «в списке дел» или срок. */
function outcome(item: FeedItem): string {
  if (item.status === "done") return "выполнено";
  if (item.status === "muted") return "не актуально";
  if (item.due) {
    const due = parseISO(item.due);
    const n = diffDays(due, today());
    return n < 0 ? `был ${dayMonth(due)}` : n === 0 ? "сегодня" : `до ${dayMonth(due)}`;
  }
  return item.listed ? "в списке дел" : "";
}

/** Лента (колокольчик): всё, о чём бот писал в чат. Пуши в чате удаляются после ответа — история здесь. */
export function Feed() {
  const { data, error, loading, reload } = useAsync(() => api.feed(), []);
  const navigate = useNavigate();

  // лента открыта — точка «есть новые» на колокольчике гаснет
  useEffect(() => {
    api.markNotificationsSeen().catch(() => undefined);
  }, []);

  let body;
  if (error) {
    body = (
      <StateView
        tone="danger"
        icon="cloud-off"
        title="Не удалось загрузить ленту"
        text="Проверьте интернет и попробуйте ещё раз."
        actions={
          <Button size="m" onClick={reload}>
            Повторить
          </Button>
        }
      />
    );
  } else if (loading || !data) {
    body = <Skeleton height={240} radius={16} />;
  } else if (data.length === 0) {
    body = (
      <StateView
        tone="primary"
        icon="inbox"
        title="Бот ещё ничего не присылал"
        text="Когда подойдёт срок, выйдет закон или изменится запись в реестре — сообщение появится здесь."
      />
    );
  } else {
    body = (
      <ListGroup>
        {data.map((item) => (
          <ListCell
            key={item.id}
            title={`${ICON[item.severity]} ${item.title}`}
            caption={`${dateTime(item.sentAt)} · ${item.subtitle}`}
            value={outcome(item)}
            chevron
            onClick={() => navigate(`/task/${item.id}`)}
          />
        ))}
      </ListGroup>
    );
  }

  return (
    <Screen title="Лента" nav="back" gap={10}>
      {body}
    </Screen>
  );
}
