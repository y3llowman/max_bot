import { Button } from "../components/Button";
import { Icon } from "../components/Icon";
import { APP_NAME, Screen } from "../components/Screen";
import { StateView } from "../components/StateView";
import { openChat } from "../max/bridge";
import s from "./Splash.module.css";

/** 01 · Старт: пока проверяем данные компании. Тот же экран — при подключении по ИНН.
 *  error: network — бэкенд недоступен; unauthorized — открыто не из MAX, узнать пользователя нечем. */
export function Splash({ error, onRetry }: { error?: "network" | "unauthorized"; onRetry?: () => void }) {
  if (error === "unauthorized") {
    return (
      <Screen title={APP_NAME}>
        <StateView
          tone="primary"
          icon="chat-back"
          title="Откройте приложение в MAX"
          text="Мы узнаём вас по данным мессенджера, поэтому приложение работает только из чата с ботом."
          actions={
            <Button size="m" variant="secondary" onClick={openChat}>
              Открыть чат с ботом
            </Button>
          }
        />
      </Screen>
    );
  }

  if (error === "network") {
    return (
      <Screen title={APP_NAME}>
        <StateView
          tone="danger"
          icon="cloud-off"
          title="Не удалось подключиться"
          text="Проверьте интернет и попробуйте ещё раз — ваши сроки никуда не денутся."
          actions={
            <Button size="m" onClick={onRetry}>
              Повторить
            </Button>
          }
        />
      </Screen>
    );
  }

  return (
    <Screen title={APP_NAME} gap={0}>
      <div className={s.brand}>
        <div className={s.logo}>
          <Icon name="radar" size={48} />
        </div>
        <h1 className="t-header">{APP_NAME}</h1>
        <p className={`t-body ${s.tagline}`}>Все налоговые сроки бизнеса — в одном окне MAX</p>
      </div>
      <div className={s.loader} role="status">
        <div className={s.track}>
          <div className={s.value} />
        </div>
        <p className={`t-note ${s.muted}`}>Проверяем данные компании…</p>
      </div>
      <p className={`t-note ${s.footer}`}>
        <Icon name="shield" size={16} />
        Данные ФНС и СФР · защищённое соединение
      </p>
    </Screen>
  );
}
