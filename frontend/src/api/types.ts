// Контракт данных мини-приложения. Бэкенд отдаёт ровно эти структуры —
// см. src/api/client.ts и раздел «API» в README.
import type { IconName } from "../components/icons";

/** Статус задачи — одна из булевых вариаций карточки в ките: overdue / soon / planned / done. */
export type TaskStatus = "overdue" | "soon" | "planned" | "done";

export interface Task {
  /** Идентификатор: только [A-Za-z0-9_-] — он же уходит в диплинк startapp=task_<id>. */
  id: string;
  title: string;
  subtitle: string;
  status: TaskStatus;
  /** Срок, YYYY-MM-DD. */
  due: string;
  /** «Ежеквартально» — чип рядом со статусом. */
  periodicity?: string;
}

export interface TaskSection {
  id: string;
  icon: IconName;
  title: string;
  caption: string;
  /** Абзацы. Если задан steps — выводится нумерованным списком. */
  body?: string[];
  steps?: string[];
  /** Сайт органа или текст закона — открывается во внешнем браузере. */
  link?: { label: string; url: string };
}

export interface TaskDetails extends Task {
  /** Полный заголовок: «Декларация по НДС за II квартал». */
  heading: string;
  sections: TaskSection[];
  /** Есть черновик документа — показываем «Подготовить документ». */
  document?: boolean;
  /** Текст уведомления после «Уже подано»: «Отмечено как поданное. Напомним об оплате 28 июля». */
  submittedNote?: string;
  /** Экран выполненной задачи. */
  done?: { title: string; text: string };
  /** Следующий срок — карточка на экране выполненной задачи. */
  next?: Task;
}

export interface Counters {
  overdue: number;
  soon: number;
  done: number;
}

export interface DashboardData {
  counters: Counters;
  /** Открытые задачи; группировку «Сегодня» / «На неделе» делает клиент. */
  tasks: Task[];
  /** Ближайший срок за пределами недели — для пустого состояния. */
  nextDue?: string;
  unread: boolean;
  /** Когда данные получены, ISO — для «Сохранено 21 июля, 18:40». */
  savedAt?: string;
}

export interface Company {
  /** «Северный ветер» в кавычках-ёлочках — так в контекстной строке. */
  name: string;
  /** ООО «Северный ветер» */
  fullName: string;
  initials: string;
  /** «УСН «Доходы минус расходы» · НДС 5%» */
  regime: string;
  inn: string;
  kpp?: string;
  ogrn: string;
  /** «41.20 — Строительство жилых и нежилых зданий» */
  okved?: string;
  /** «Микропредприятие» */
  category?: string;
  /** «16–25 человек» */
  headcount?: string;
  /** «Республика Татарстан» */
  region?: string;
  /** Режим или численность не указаны — без ответов бот видит не все обязанности. */
  needsAnswers?: boolean;
  source: { name: string; demo: boolean; updatedAt: string };
  counterparties: number;
}

export type RemindMode = "d30-7-1" | "d7-3-1" | "d3-0" | "d0";

export interface NotificationSettings {
  chat: boolean;
  push: boolean;
  email: boolean;
  emailAddress?: string;
  quiet: boolean;
  /** «22:00–08:00» */
  quietRange: string;
  remind: RemindMode;
}
