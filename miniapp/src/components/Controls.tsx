import s from "./Controls.module.css";

/** Toggle 48×28 / r14, ручка 24. Визуальный: роль switch несёт вся строка списка. */
export function Toggle({ checked }: { checked: boolean }) {
  return (
    <span className={`${s.toggle} ${checked ? s.on : ""}`} aria-hidden="true">
      <span className={s.knob} />
    </span>
  );
}

/** Radio 22: включённый — обводка 2 primary и точка, выключенный — обводка 1.5 text/secondary. */
export function Radio({ checked }: { checked: boolean }) {
  return <span className={`${s.radio} ${checked ? s.radioOn : ""}`} aria-hidden="true" />;
}
