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
  close(): void;
  shareMaxContent(params: { text?: string; link?: string }): void;
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

let relaunched: string | null = null;

export function initData(): string {
  return relaunched ?? wa()?.initData ?? "";
}

function startParamOf(data: string): string | undefined {
  try {
    return new URLSearchParams(decodeURIComponent(data)).get("start_param") || undefined;
  } catch {
    return undefined;
  }
}

export function startParam(): string | undefined {
  return relaunched ? startParamOf(relaunched) : wa()?.initDataUnsafe.start_param || undefined;
}

export function onRelaunch(cb: (startParam: string | undefined) => void): void {
  window.addEventListener("hashchange", (e) => {
    const data = new URLSearchParams(new URL(e.newURL).hash.slice(1)).get("WebAppData");
    if (!data || !wa()) return;
    relaunched = data;
    cb(startParamOf(data));
  });
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

export function openLink(url: string): void {
  const app = wa();
  if (app) app.openLink(url);
  else window.open(url, "_blank", "noopener");
}

export function openChat(): void {
  const app = wa();
  if (app) {
    app.openMaxLink(chatUrl());
    app.close();
  } else window.open(chatUrl(), "_blank", "noopener");
}

export const haptic = {
  success: () => wa()?.HapticFeedback.notificationOccurred("success"),
  error: () => wa()?.HapticFeedback.notificationOccurred("error"),
  select: () => wa()?.HapticFeedback.selectionChanged(),
};
