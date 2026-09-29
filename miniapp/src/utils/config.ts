const params = new URLSearchParams(window.location.search);

export type ForcedState = "loading" | "empty" | "error";

export const config = {
  apiUrl: (import.meta.env.VITE_API_URL as string | undefined) ?? "",
  botName: (import.meta.env.VITE_MAX_BOT_NAME as string | undefined) ?? "",
  forcedState: params.get("state") as ForcedState | null,
  forcedTheme: params.get("theme") as "light" | "dark" | null,
  forcedPlatform: params.get("platform") as "ios" | "android" | null,
  mockToday: params.get("today") ?? "2026-07-22",
};

export const isMock = !config.apiUrl;
