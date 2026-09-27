import type { ReactNode } from "react";
import { useDockHeight } from "../utils/dock";
import s from "./ActionBar.module.css";

/** Action Bar — нижняя панель вложенных экранов: разделитель, отступы 12/20, кнопки 52. */
export function ActionBar({ children }: { children: ReactNode }) {
  const ref = useDockHeight<HTMLDivElement>();
  return (
    <div ref={ref} className={s.bar}>
      {children}
    </div>
  );
}

/** Кнопки в ряд поровну: «Уже подано» + «Сформировать». */
export function ActionRow({ children }: { children: ReactNode }) {
  return <div className={s.row}>{children}</div>;
}

export function ActionNote({ children }: { children: ReactNode }) {
  return <p className={`t-note ${s.note}`}>{children}</p>;
}
