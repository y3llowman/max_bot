import s from "./Segmented.module.css";

interface Props<T extends string> {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}

/** Segmented: 48 / r12, подложка surface-2, активный сегмент 40 / r8 с рамкой. */
export function Segmented<T extends string>({ options, value, onChange, label }: Props<T>) {
  return (
    <div className={s.segmented} role="tablist" aria-label={label}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="tab"
            aria-selected={active}
            className={`${s.segment} ${active ? `${s.active} t-detail-strong` : "t-detail"}`}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
