// Настройки запуска. Параметры в адресе — для ревью дизайна и демо, их можно
// комбинировать: index.html?state=empty&theme=dark&platform=android#/tasks
const params = new URLSearchParams(window.location.search);

export type ForcedState = "loading" | "empty" | "error";

export const config = {
  apiUrl: (import.meta.env.VITE_API_URL as string | undefined) ?? "",
  botName: (import.meta.env.VITE_MAX_BOT_NAME as string | undefined) ?? "",
  /** Состояние экранов на моках: загрузка, пусто или ошибка (S1–S6 в макетах). */
  forcedState: params.get("state") as ForcedState | null,
  forcedTheme: params.get("theme") as "light" | "dark" | null,
  forcedPlatform: params.get("platform") as "ios" | "android" | null,
  /** «Сегодня» для моков. По умолчанию — дата из макетов, чтобы экраны совпадали с дизайном. */
  mockToday: params.get("today") ?? "2026-07-22",
};

export const isMock = !config.apiUrl;
