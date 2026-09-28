// Интерфейс API и ошибки — общий модуль для реального клиента и моков,
// чтобы они не импортировали друг друга.
import type {
  Company, DashboardData, DatedTask, FeedItem, NotificationSettings, ProfileForm, ProfileUpdate, TaskDetails,
} from "./types";

/** unavailable — не ответил внешний источник (реестр ФНС), server — ошибка нашего сервера,
 *  conflict — компанию уже подключил другой пользователь, invalid — сервер не принял данные формы. */
export type ApiErrorCode = "not_found" | "network" | "server" | "unavailable" | "unauthorized" | "conflict" | "invalid";

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
  calendar(from: string, to: string): Promise<DatedTask[]>;
  company(): Promise<Company>;
  /** Перечитать реестр МСП; выписку ЕГРЮЛ сервер проверит в фоне, находки придут в чат. */
  refreshCompany(): Promise<Company>;
  notifications(): Promise<NotificationSettings>;
  saveNotifications(settings: NotificationSettings): Promise<void>;
  /** Лента открыта — гасим точку на колокольчике. */
  markNotificationsSeen(): Promise<void>;
  /** Лента: о чём бот писал в чат за 90 дней, свежее сверху. */
  feed(): Promise<FeedItem[]>;
  /** «Данные компании»: режим, численность, ОКВЭД, регион, признаки. */
  profileForm(): Promise<ProfileForm>;
  saveProfile(update: ProfileUpdate): Promise<Company>;
  /** «В список дел»: событие без срока становится задачей на главной. */
  addToList(id: string): Promise<void>;
  markSubmitted(id: string): Promise<void>;
  undoSubmitted(id: string): Promise<void>;
  /** Сформировать документ — бот пришлёт его в чат. */
  generateDocument(id: string): Promise<void>;
}
