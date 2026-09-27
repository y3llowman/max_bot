import { useCallback, useEffect, type CSSProperties, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { backButton, inMax } from "../max/bridge";
import { Icon } from "./Icon";
import s from "./Screen.module.css";

interface Props {
  /** Заголовок в шапке MAX: название приложения на верхнем уровне, «Задача», «Календарь»… */
  title: string;
  /** По заметке дизайнера: верхний уровень — крестик, вложенные — стрелка ‹. */
  nav?: "close" | "back";
  /** Вертикальный шаг между блоками контента. */
  gap?: number;
  /** Нижняя панель вложенного экрана. Таббар добавляет раскладка разделов. */
  bottom?: ReactNode;
  children: ReactNode;
}

export const APP_NAME = "Хакатон MAX 267";

export function useGoBack(fallback = "/tasks") {
  const navigate = useNavigate();
  return useCallback(() => {
    // react-router хранит номер записи истории в history.state.idx
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0;
    if (idx > 0) navigate(-1);
    else navigate(fallback, { replace: true });
  }, [navigate, fallback]);
}

export function Screen({ title, nav = "close", gap = 12, bottom, children }: Props) {
  const goBack = useGoBack();

  useEffect(() => {
    document.title = title;
  }, [title]);

  // Во вложенных экранах стрелку рисует MAX — подписываемся на её нажатие.
  useEffect(() => {
    if (nav !== "back") return;
    backButton.show(goBack);
    return () => backButton.hide(goBack);
  }, [nav, goBack]);

  return (
    <div className={s.screen}>
      {!inMax() && <DevChrome title={title} nav={nav} onBack={goBack} />}
      <main className={s.content} style={{ "--gap": `${gap}px` } as CSSProperties}>
        {children}
      </main>
      {bottom}
    </div>
  );
}

/** Шапка MAX для браузера. Внутри клиента её рисует сам MAX, поэтому там её нет. */
function DevChrome({ title, nav, onBack }: { title: string; nav: "close" | "back"; onBack: () => void }) {
  return (
    <header className={s.chrome}>
      <button
        type="button"
        className={s.chromeButton}
        onClick={nav === "back" ? onBack : undefined}
        aria-label={nav === "back" ? "Назад" : "Закрыть"}
      >
        <Icon name={nav === "back" ? "chevron-left" : "close"} size={24} />
      </button>
      <span className={`t-title ${s.chromeTitle}`}>
        {title}
        <svg className={s.verified} width="16" height="16" viewBox="0 0 16 16" aria-label="Проверенный бот">
          <circle cx="8" cy="8" r="8" fill="currentColor" />
          <path d="M4.8 8.2l2.1 2.1 4.3-4.4" fill="none" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span className={s.chromeButton} aria-hidden="true">
        <Icon name="more-circle" size={24} />
      </span>
    </header>
  );
}
