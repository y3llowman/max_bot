import s from "./Controls.module.css";

export function Toggle({ checked }: { checked: boolean }) {
  return (
    <span className={`${s.toggle} ${checked ? s.on : ""}`} aria-hidden="true">
      <span className={s.knob} />
    </span>
  );
}

export function Radio({ checked }: { checked: boolean }) {
  return <span className={`${s.radio} ${checked ? s.radioOn : ""}`} aria-hidden="true" />;
}
