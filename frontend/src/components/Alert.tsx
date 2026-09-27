import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import s from "./Alert.module.css";

type Tone = "error" | "warning" | "info" | "success";

const ICON: Record<Tone, IconName> = {
  error: "alert-circle",
  warning: "alert-triangle",
  info: "info",
  success: "check-circle",
};

interface AlertProps {
  tone: Tone;
  title: string;
  children: ReactNode;
  action?: { label: string; onClick: () => void };
}

export function Alert({ tone, title, children, action }: AlertProps) {
  return (
    <div className={`${s.alert} ${s[tone]}`} role={tone === "error" ? "alert" : "note"}>
      <Icon name={ICON[tone]} size={20} className={s.icon} />
      <div className={s.text}>
        <p className="t-detail-strong">{title}</p>
        <p className="t-description">{children}</p>
        {action && (
          <button type="button" className={`t-detail-strong ${s.action}`} onClick={action.onClick}>
            {action.label}
          </button>
        )}
      </div>
    </div>
  );
}
