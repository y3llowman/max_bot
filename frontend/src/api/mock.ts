// Моковые данные — те же, что на макетах: «сегодня» 22 июля 2026, компания
// «Северный ветер». Работают, пока не задан VITE_API_URL.
// Демо-сценарии: ИНН 0000000000 — «компания не найдена»; ?state=loading|empty|error
// в адресе — состояния загрузки, пустого экрана и ошибки из макетов.
import { config } from "../utils/config";
import { load, save } from "../utils/storage";
import type { Company, DashboardData, NotificationSettings, Task, TaskDetails, TaskSection } from "./types";
import { ApiError, type Api } from "./contract";

const LATENCY = 450;

const company: Company = {
  name: "«Северный ветер»",
  fullName: "ООО «Северный ветер»",
  initials: "СВ",
  regime: "УСН «Доходы минус расходы» · НДС 5%",
  inn: "7701234567",
  kpp: "770101001",
  ogrn: "1177746123456",
  okved: "46.90 — Торговля оптовая неспециализированная",
  category: "Малое предприятие",
  headcount: "36–100 человек",
  region: "Москва",
  source: { name: "ФНС", demo: true, updatedAt: "2026-07-22T08:12:00" },
  counterparties: 8,
};

const tasks: Task[] = [
  { id: "req-12-45-3817", title: "Ответ на требование ФНС", subtitle: "№ 12-45/3817 · пояснения", status: "overdue", due: "2026-07-20" },
  { id: "ndfl-notice-2207", title: "Уведомление по НДФЛ", subtitle: "23.06–22.07 · КНД 1110355", status: "soon", due: "2026-07-22" },
  { id: "reconciliation-alfa", title: "Акт сверки", subtitle: "«Альфа-Трейд» · запрос", status: "planned", due: "2026-07-24" },
  { id: "vat-2026-q2", title: "Декларация по НДС", subtitle: "За II квартал 2026", status: "soon", due: "2026-07-27" },
  { id: "enp-2607", title: "Уплата ЕНП", subtitle: "Налоги и взносы · 184 320 ₽", status: "planned", due: "2026-07-28" },
  { id: "ndfl-notice-2208", title: "Уведомление по НДФЛ", subtitle: "23.07–22.08 · КНД 1110355", status: "planned", due: "2026-08-25" },
  // выполненные
  { id: "usn-advance-h1", title: "Аванс по УСН", subtitle: "За полугодие · 96 400 ₽", status: "done", due: "2026-07-15" },
  { id: "sfr-personal-06", title: "Персонифицированные сведения", subtitle: "За июнь · СФР", status: "done", due: "2026-07-10" },
  { id: "ndfl-pay-0630", title: "Уплата НДФЛ", subtitle: "23.06–30.06 · 18 400 ₽", status: "done", due: "2026-07-03" },
  { id: "enp-2606", title: "Уплата ЕНП", subtitle: "Налоги и взносы · 171 050 ₽", status: "done", due: "2026-06-29" },
  { id: "ndfl-notice-2206", title: "Уведомление по НДФЛ", subtitle: "23.05–22.06 · КНД 1110355", status: "done", due: "2026-06-25" },
  { id: "reconciliation-beta", title: "Акт сверки", subtitle: "«Бета-Снаб» · запрос", status: "done", due: "2026-06-24" },
  { id: "req-11-02-2210", title: "Ответ на требование ФНС", subtitle: "№ 11-02/2210 · документы", status: "done", due: "2026-06-19" },
  { id: "sfr-personal-05", title: "Персонифицированные сведения", subtitle: "За май · СФР", status: "done", due: "2026-06-10" },
  { id: "ndfl-pay-0605", title: "Уплата НДФЛ", subtitle: "23.05–31.05 · 16 900 ₽", status: "done", due: "2026-06-05" },
  { id: "enp-2605", title: "Уплата ЕНП", subtitle: "Налоги и взносы · 168 300 ₽", status: "done", due: "2026-05-28" },
  { id: "ndfl-notice-2205", title: "Уведомление по НДФЛ", subtitle: "23.04–22.05 · КНД 1110355", status: "done", due: "2026-05-25" },
  { id: "sfr-personal-04", title: "Персонифицированные сведения", subtitle: "За апрель · СФР", status: "done", due: "2026-05-12" },
];

const vatSections: TaskSection[] = [
  {
    id: "steps", icon: "tasks", title: "Что сделать", caption: "4 шага · около 20 минут",
    steps: [
      "Сверьте счета-фактуры за апрель–июнь в книгах покупок и продаж.",
      "Проверьте вычеты и восстановленный НДС.",
      "Сформируйте декларацию в бухгалтерской программе.",
      "Подпишите и отправьте через оператора ЭДО.",
    ],
  },
  {
    id: "how", icon: "file", title: "Как отправить", caption: "Только электронно, через ЭДО",
    body: ["Декларацию по НДС принимают только в электронном виде через оператора ЭДО. Бумажная считается непредставленной."],
  },
  {
    id: "law", icon: "scale", title: "Правовое обоснование", caption: "Налоговый кодекс, ст. 174",
    body: [
      "Декларация подаётся не позднее 25-го числа месяца, следующего за кварталом (п. 5 ст. 174 НК РФ). 25 июля 2026 — суббота, поэтому срок переносится на понедельник, 27 июля.",
      "Норма сверена 12.07.2026 · publication.pravo.gov.ru · демо-данные",
    ],
  },
  {
    id: "risks", icon: "alert-triangle", title: "Риски при задержке", caption: "Штраф и блокировка счёта",
    body: [
      "Штраф — 5% от суммы налога за каждый месяц задержки: не меньше 1 000 ₽ и не больше 30%.",
      "Если задержка больше 20 рабочих дней, налоговая может заблокировать счёт компании.",
    ],
  },
];

function genericSections(task: Task): TaskSection[] {
  return [
    {
      id: "steps", icon: "tasks", title: "Что сделать", caption: "3 шага",
      steps: [
        "Проверьте данные в шаблоне — мы заполнили их из профиля.",
        "Подпишите документ.",
        "Отправьте через оператора ЭДО.",
      ],
    },
    { id: "how", icon: "file", title: "Как отправить", caption: "Электронно, через ЭДО", body: [`${task.title}: отправка через оператора ЭДО или личный кабинет налогоплательщика.`] },
    { id: "law", icon: "scale", title: "Правовое обоснование", caption: "Норма и дата сверки", body: ["Норма подставляется из базы правил вместе с датой сверки · демо-данные"] },
    { id: "risks", icon: "alert-triangle", title: "Риски при задержке", caption: "Штраф", body: ["Размер штрафа подставляется из базы правил · демо-данные"] },
  ];
}

// Отметки «Уже подано», сделанные в этой сессии.
const submitted = new Set<string>();
let notifications: NotificationSettings = {
  chat: true, push: true, email: false, emailAddress: "buh@severveter.ru",
  quiet: true, quietRange: "22:00–08:00", remind: "d30-7-1",
};

function withStatus(t: Task): Task {
  return submitted.has(t.id) ? { ...t, status: "done" } : t;
}

function delay<T>(value: T | (() => T)): Promise<T> {
  if (config.forcedState === "loading") return new Promise(() => {});
  return new Promise((resolve, reject) =>
    setTimeout(() => {
      if (config.forcedState === "error") {
        reject(new ApiError("network", "Сервис ФНС не отвечает"));
        return;
      }
      try {
        resolve(typeof value === "function" ? (value as () => T)() : value);
      } catch (e) {
        reject(e);
      }
    }, LATENCY),
  );
}

function ok<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), LATENCY));
}

const SESSION_KEY = "mock-session";

/** «Сейчас» в мок-мире: дата из макетов, время текущее — чтобы подписи были «сегодня в 14:03». */
function mockNow(): string {
  const now = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${config.mockToday}T${p(now.getHours())}:${p(now.getMinutes())}:00`;
}

export const mockApi: Api = {
  session: () => ok(load<Company>(SESSION_KEY)),

  connect: (inn) =>
    new Promise((resolve, reject) =>
      setTimeout(() => {
        if (/^0+$/.test(inn)) {
          reject(new ApiError("not_found", "Компания не найдена"));
          return;
        }
        const c = { ...company, inn };
        save(SESSION_KEY, c);
        resolve(c);
      }, 1400),
    ),

  dashboard: () =>
    delay<DashboardData>(() => {
      const all = tasks.map(withStatus);
      if (config.forcedState === "empty") {
        return { counters: { overdue: 0, soon: 0, done: 12 }, tasks: [], nextDue: "2026-08-25", unread: false };
      }
      return {
        counters: {
          overdue: all.filter((t) => t.status === "overdue").length,
          soon: all.filter((t) => t.status === "soon").length,
          done: all.filter((t) => t.status === "done").length,
        },
        tasks: all.filter((t) => t.status !== "done"),
        nextDue: "2026-08-25",
        unread: true,
        savedAt: mockNow(),
      };
    }),

  task: (id) =>
    delay<TaskDetails>(() => {
      const base = tasks.find((t) => t.id === id);
      if (!base) throw new ApiError("not_found", "Задача не найдена");
      const t = withStatus(base);
      const isVat = t.id === "vat-2026-q2";
      return {
        ...t,
        heading: isVat ? "Декларация по НДС за II квартал" : t.title,
        periodicity: isVat ? "Ежеквартально" : undefined,
        document: t.id.startsWith("ndfl-notice"),
        sections: isVat ? vatSections : genericSections(t),
        submittedNote: isVat ? "Отмечено как поданное. Напомним об оплате 28 июля" : "Отмечено как выполненное",
        done: isVat
          ? { title: "Готово, декларация принята", text: "Налоговая приняла декларацию по НДС 25 июля в 14:05. Квитанция сохранена в разделе «Документы»." }
          : { title: "Готово", text: "Задача отмечена как выполненная. О следующем сроке напомним в чате MAX." },
        next: tasks.map(withStatus).find((n) => n.status !== "done" && n.id !== t.id && n.due >= t.due),
      };
    }),

  // в ?state=empty ближайших сроков нет, но следующий срок 25 августа остаётся — как в S2 и S6
  calendar: (from, to) =>
    delay(() =>
      tasks
        .map(withStatus)
        .filter((t) => t.due >= from && t.due <= to)
        .filter((t) => config.forcedState !== "empty" || t.due >= "2026-08-25"),
    ),

  company: () => delay(() => load<Company>(SESSION_KEY) ?? company),

  refreshCompany: () => {
    const c = { ...(load<Company>(SESSION_KEY) ?? company), source: { ...company.source, updatedAt: mockNow() } };
    save(SESSION_KEY, c);
    return ok(c);
  },

  notifications: () => delay(() => notifications),

  saveNotifications: (next) => {
    notifications = next;
    return ok(undefined);
  },

  markSubmitted: (id) => {
    submitted.add(id);
    return ok(undefined);
  },

  undoSubmitted: (id) => {
    submitted.delete(id);
    return ok(undefined);
  },

  generateDocument: () => ok(undefined),
};

/** Для S3: если в mock-режиме форсирована ошибка, а сохранённой версии нет — подкладываем её. */
export function seedMockCache(): DashboardData {
  return {
    counters: { overdue: 1, soon: 2, done: 12 },
    tasks: tasks.filter((t) => t.status !== "done"),
    nextDue: "2026-08-25",
    unread: true,
    savedAt: "2026-07-21T18:40:00",
  };
}
