// Даты храним строками YYYY-MM-DD и разбираем в локальное время:
// так «20 июля» не уезжает на 19-е из-за часового пояса.
import { config, isMock } from "./config";

const MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
  "августа", "сентября", "октября", "ноября", "декабря"];
const MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
  "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
export const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

export function parseISO(s: string): Date {
  const [y, m, d] = s.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function toISO(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function today(): Date {
  return isMock ? parseISO(config.mockToday) : startOfDay(new Date());
}

export function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}

export function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}

/** Понедельник недели, в которую попадает дата. */
export function startOfWeek(d: Date): Date {
  return addDays(d, -((d.getDay() + 6) % 7));
}

export function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

export function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function diffDays(a: Date, b: Date): number {
  return Math.round((startOfDay(a).getTime() - startOfDay(b).getTime()) / 86_400_000);
}

export function weekdayShort(d: Date): string {
  return WEEKDAYS[(d.getDay() + 6) % 7];
}

/** «20 июля» */
export function dayMonth(d: Date): string {
  return `${d.getDate()} ${MONTHS_GEN[d.getMonth()]}`;
}

/** «Пн, 20 июля» */
export function dayTitle(d: Date): string {
  return `${weekdayShort(d)}, ${dayMonth(d)}`;
}

/** «Июль 2026» */
export function monthTitle(d: Date): string {
  return `${MONTHS_NOM[d.getMonth()]} ${d.getFullYear()}`;
}

/** «20 – 26 июля» или «27 июля – 2 августа» */
export function weekRange(monday: Date): string {
  const sunday = addDays(monday, 6);
  return monday.getMonth() === sunday.getMonth()
    ? `${monday.getDate()} – ${dayMonth(sunday)}`
    : `${dayMonth(monday)} – ${dayMonth(sunday)}`;
}

/** «21 июля, 18:40» */
export function dateTime(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${dayMonth(d)}, ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** «сегодня в 08:12» / «вчера в 18:40» / «21 июля в 18:40» */
export function updatedAt(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  const time = `${p(d.getHours())}:${p(d.getMinutes())}`;
  const days = diffDays(today(), d);
  if (days === 0) return `сегодня в ${time}`;
  if (days === 1) return `вчера в ${time}`;
  return `${dayMonth(d)} в ${time}`;
}

export function plural(n: number, forms: [string, string, string]): string {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return forms[2];
  if (b > 1 && b < 5) return forms[1];
  if (b === 1) return forms[0];
  return forms[2];
}

const DAYS: [string, string, string] = ["день", "дня", "дней"];

/** «осталось 5 дней» / «срок сегодня» / «просрочено на 2 дня» */
export function timeLeft(due: Date, now = today()): string {
  const n = diffDays(due, now);
  if (n > 0) return `осталось ${n} ${plural(n, DAYS)}`;
  if (n === 0) return "срок сегодня";
  return `просрочено на ${-n} ${plural(-n, DAYS)}`;
}
