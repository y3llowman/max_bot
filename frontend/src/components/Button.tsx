import type { ButtonHTMLAttributes } from "react";
import { Icon, type IconName } from "./Icon";
import s from "./Button.module.css";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger";
  size?: "l" | "m";
  block?: boolean;
}

export function Button({ variant = "primary", size = "l", block, className, type = "button", ...rest }: ButtonProps) {
  const cls = [s.button, s[size], s[variant], block && s.block, className].filter(Boolean).join(" ");
  return <button type={type} className={cls} {...rest} />;
}

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: IconName;
  /** Обязательна: у кнопки без текста должно быть имя для скринридера. */
  label: string;
  size?: number;
  outlined?: boolean;
}

export function IconButton({ icon, label, size = 24, outlined, className, type = "button", ...rest }: IconButtonProps) {
  const cls = [s.iconButton, outlined && s.iconButtonOutlined, className].filter(Boolean).join(" ");
  return (
    <button type={type} className={cls} aria-label={label} title={label} {...rest}>
      <Icon name={icon} size={size} />
    </button>
  );
}
