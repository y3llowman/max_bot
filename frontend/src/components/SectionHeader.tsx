import type { ReactNode } from "react";
import s from "./SectionHeader.module.css";

interface Props {
  title: string;
  count?: number;
  /** Дополнение справа от заголовка — например, чип «Сегодня». */
  children?: ReactNode;
}

export function SectionHeader({ title, count, children }: Props) {
  return (
    <div className={s.header}>
      <h2 className="t-title">{title}</h2>
      {count !== undefined && <span className={s.count}>{count}</span>}
      {children}
    </div>
  );
}
