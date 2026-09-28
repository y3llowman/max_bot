import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import s from "./StateView.module.css";

type Tone = "success" | "danger" | "warning" | "primary";

interface Props {
  tone: Tone;
  icon: IconName;
  title: string;
  text: string;
  /** Под текстом: чип «Сохранено…» или плашка «Ближайший срок…». */
  extra?: ReactNode;
  actions?: ReactNode;
}

/** Пустое состояние и ошибка (S2, S3, S5, S6): иллюстрация 119 с кольцом 88, заголовок,
 *  объяснение и выход — по заметке дизайнера у ошибки всегда есть повтор, сохранённые данные или чат. */
export function StateView({ tone, icon, title, text, extra, actions }: Props) {
  return (
    <div className={s.state}>
      <div className={s.illustration} aria-hidden="true">
        <div className={`${s.ring} ${s[tone]}`}>
          <Icon name={icon} size={40} />
        </div>
      </div>
      <h2 className={`t-subheader ${s.title}`}>{title}</h2>
      <p className={`t-detail ${s.text}`}>{text}</p>
      {extra && <div className={s.extra}>{extra}</div>}
      {actions && <div className={s.actions}>{actions}</div>}
    </div>
  );
}

/** Плашка «Ближайший срок — 25 августа» из S2. */
export function NextDuePill({ children }: { children: string }) {
  return (
    <span className={`t-detail ${s.pill}`}>
      <Icon name="calendar" size={18} className={s.pillIcon} />
      {children}
    </span>
  );
}
