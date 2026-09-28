// Интерфейс API и ошибки — общий модуль для реального клиента и моков,
// чтобы они не импортировали друг друга.
import type { Company, DashboardData, NotificationSettings, Task, TaskDetails } from "./types";

/** unavailable — не ответил внешний источник (реестр ФНС), server — ошибка нашего сервера. */
export type ApiErrorCode = "not_found" | "network" | "server" | "unavailable" | "unauthorized";

export class ApiError extends Error {
  code: ApiErrorCode;
  constructor(code: ApiErrorCode, message: string) {
    super(message);
    this.code = code;
  }
}

export interface Api {
  /** Подключённая компания или null — тогда показываем экран подключения. */
  session(): Promise<Company | null>;
  connect(inn: string): Promise<Company>;
  dashboard(): Promise<DashboardData>;
  task(id: string): Promise<TaskDetails>;
  /** Задачи со сроком в интервале, включая выполненные. Даты YYYY-MM-DD. */
  calendar(from: string, to: string): Promise<Task[]>;
  company(): Promise<Company>;
  /** Перечитать реестр МСП; выписку ЕГРЮЛ сервер проверит в фоне, находки придут в чат. */
  refreshCompany(): Promise<Company>;
  notifications(): Promise<NotificationSettings>;
  saveNotifications(settings: NotificationSettings): Promise<void>;
  /** Экран «Уведомления» открыт — гасим точку на колокольчике. */
  markNotificationsSeen(): Promise<void>;
  markSubmitted(id: string): Promise<void>;
  undoSubmitted(id: string): Promise<void>;
  /** Сформировать документ — бот пришлёт его в чат. */
  generateDocument(id: string): Promise<void>;
}
