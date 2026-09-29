import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import s from "./StateView.module.css";

type Tone = "success" | "danger" | "warning" | "primary";

interface Props {
  tone: Tone;
  icon: IconName;
  title: string;
  text: string;
  extra?: ReactNode;
  actions?: ReactNode;
}

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

export function NextDuePill({ children }: { children: string }) {
  return (
    <span className={`t-detail ${s.pill}`}>
      <Icon name="calendar" size={18} className={s.pillIcon} />
      {children}
    </span>
  );
}
