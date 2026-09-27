import type { ReactNode } from "react";
import { Icon } from "./Icon";
import s from "./List.module.css";

/** Группа строк на карточке: r16, разделители на всю внутреннюю ширину. */
export function ListGroup({ children, label, radio }: { children: ReactNode; label?: string; radio?: boolean }) {
  return (
    <div className={s.group} role={radio ? "radiogroup" : label ? "group" : undefined} aria-label={label}>
      {children}
    </div>
  );
}

interface CellProps {
  title: string;
  caption?: string;
  value?: string;
  /** Элемент слева: радио. */
  lead?: ReactNode;
  /** Элемент справа: переключатель. */
  trail?: ReactNode;
  chevron?: boolean;
  onClick?: () => void;
  /** Роль и состояние для скринридера: switch/radio. */
  role?: "switch" | "radio";
  checked?: boolean;
  disabled?: boolean;
  /** Нативный выбор поверх строки — для темы и тихих часов. */
  select?: { value: string; options: { value: string; label: string }[]; onChange: (v: string) => void };
}

/** List Cell: 48 для навигации, 56 с переключателем, 52 с радио — как в макетах. */
export function ListCell({ title, caption, value, lead, trail, chevron, onClick, role, checked, disabled, select }: CellProps) {
  const content = (
    <>
      {lead}
      <span className={s.text}>
        <span className="t-body">{title}</span>
        {caption && <span className={`t-note ${s.caption}`}>{caption}</span>}
      </span>
      {value && <span className={`t-detail ${s.value}`}>{value}</span>}
      {trail}
      {chevron && <Icon name="chevron-right" size={20} className={s.chevron} />}
    </>
  );

  const cls = `${s.cell} ${lead ? s.withLead : ""}`;

  if (select) {
    return (
      <label className={`${cls} ${s.interactive} ${disabled ? s.disabled : ""}`}>
        {content}
        <select
          className={s.select}
          value={select.value}
          disabled={disabled}
          onChange={(e) => select.onChange(e.target.value)}
          aria-label={title}
        >
          {select.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (onClick) {
    return (
      <button
        type="button"
        className={`${cls} ${s.interactive}`}
        onClick={onClick}
        role={role}
        aria-checked={role ? checked : undefined}
        disabled={disabled}
      >
        {content}
      </button>
    );
  }

  return <div className={cls}>{content}</div>;
}
