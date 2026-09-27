// Обёртка над MAX Bridge (window.WebApp, скрипт st.max.ru/js/max-web-app.js).
// Методы — по https://dev.max.ru/docs/webapps/bridge. Вне клиента MAX скрипт
// тоже создаёт window.WebApp, но с пустым initData — так и отличаем «внутри MAX».
// Всё, чего нет вне MAX, заменено безопасными заглушками, чтобы приложение
// открывалось в обычном браузере для разработки и ревью дизайна.
import { config } from "../utils/config";

export type Platform = "ios" | "android" | "desktop" | "web";

interface WebAppBridge {
  initData: string;
  initDataUnsafe: { start_param?: string; user?: { id: number; first_name?: string } };
  platform: Platform;
  version: string;
  BackButton: {
    isVisible: boolean;
    show(): void;
    hide(): void;
    onClick(cb: () => void): void;
    offClick(cb: () => void): void;
  };
  openLink(url: string): void;
  openMaxLink(url: string): void;
  shareMaxContent(params: { text?: string; link?: string }): void;
  openCodeReader(fileSelect?: boolean): Promise<string> | string;
  HapticFeedback: {
    impactOccurred(style: "soft" | "light" | "medium" | "heavy" | "rigid"): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
    selectionChanged(): void;
  };
}

declare global {
  interface Window {
    WebApp?: WebAppBridge;
  }
}

function wa(): WebAppBridge | undefined {
  const app = window.WebApp;
  return app && app.initData ? app : undefined;
}

export function inMax(): boolean {
  return !!wa();
}

export function platform(): Platform {
  if (config.forcedPlatform) return config.forcedPlatform;
  const p = wa()?.platform;
  if (p) return p;
  const ua = navigator.userAgent;
  if (/iPhone|iPad|iPod/.test(ua)) return "ios";
  if (/Android/.test(ua)) return "android";
  return "web";
}

/** Сырая строка initData — уходит на бэкенд для проверки подписи. */
export function initData(): string {
  return wa()?.initData ?? "";
}

/** Параметр диплинка https://max.ru/<бот>?startapp=<payload>: до 512 символов, [A-Za-z0-9_-]. */
export function startParam(): string | undefined {
  return wa()?.initDataUnsafe.start_param || undefined;
}

export const backButton = {
  show(cb: () => void) {
    const app = wa();
    if (!app) return;
    app.BackButton.onClick(cb);
    app.BackButton.show();
  },
  hide(cb: () => void) {
    const app = wa();
    if (!app) return;
    app.BackButton.offClick(cb);
    app.BackButton.hide();
  },
};

export function chatUrl(): string {
  return config.botName ? `https://max.ru/${config.botName}` : "https://max.ru";
}

/** Внешняя ссылка (сайт ФНС, текст закона) — во внешнем браузере. */
export function openLink(url: string): void {
  const app = wa();
  if (app) app.openLink(url);
  else window.open(url, "_blank", "noopener");
}

/** «В чат MAX»: открыть диалог с ботом внутри мессенджера. */
export function openChat(): void {
  const app = wa();
  if (app) app.openMaxLink(chatUrl());
  else window.open(chatUrl(), "_blank", "noopener");
}

/** Сканер QR клиента MAX. null — сканер недоступен (браузер) или пользователь закрыл его. */
export async function scanQr(): Promise<string | null> {
  const app = wa();
  if (!app) return null;
  try {
    const result = await app.openCodeReader(false);
    return result || null;
  } catch {
    return null;
  }
}

export function canScanQr(): boolean {
  return inMax();
}

export const haptic = {
  success: () => wa()?.HapticFeedback.notificationOccurred("success"),
  error: () => wa()?.HapticFeedback.notificationOccurred("error"),
  select: () => wa()?.HapticFeedback.selectionChanged(),
};
