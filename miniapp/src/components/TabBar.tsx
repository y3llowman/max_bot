import { NavLink } from "react-router-dom";
import { platform } from "../max/bridge";
import { useDockHeight } from "../utils/dock";
import { Icon, type IconName } from "./Icon";
import s from "./TabBar.module.css";

const TABS: { to: string; label: string; icon: IconName }[] = [
  { to: "/tasks", label: "Обязанности", icon: "tasks" },
  { to: "/calendar", label: "Календарь", icon: "calendar" },
  { to: "/profile", label: "Профиль", icon: "user" },
];

/** Таббар — только на экранах верхнего уровня. На Android — индикатор-пилюля (Material), на остальных — iOS-вариант. */
export function TabBar() {
  const android = platform() === "android";
  const ref = useDockHeight<HTMLElement>();
  return (
    <nav ref={ref} className={`${s.bar} ${android ? s.android : s.ios}`} aria-label="Разделы">
      {TABS.map((t) => (
        <NavLink key={t.to} to={t.to} className={({ isActive }) => `${s.tab} ${isActive ? s.active : ""}`}>
          <span className={s.indicator}>
            <Icon name={t.icon} size={24} />
          </span>
          <span className={s.label}>{t.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
