import { useId } from "react";
import { IconButton } from "./Button";
import { Icon } from "./Icon";
import s from "./InnField.module.css";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  onSubmit?: () => void;
  onScan?: () => void;
  error?: string | null;
  disabled?: boolean;
}

/** Поле ИНН (Input/Default · Focus · Error · Disabled) и кнопка QR рядом. Высота 52, r12. */
export function InnField({ value, onChange, onBlur, onSubmit, onScan, error, disabled }: Props) {
  const id = useId();
  const hintId = `${id}-hint`;

  return (
    <div className={s.field}>
      <label className={`t-label ${s.label}`} htmlFor={id}>
        ИНН организации или ИП
      </label>
      <div className={s.row}>
        <div className={`${s.box} ${error ? s.error : ""} ${disabled ? s.disabled : ""}`}>
          <input
            id={id}
            className={`t-body ${s.input}`}
            value={value}
            inputMode="numeric"
            autoComplete="off"
            enterKeyHint="go"
            maxLength={12}
            placeholder="Введите 10 или 12 цифр"
            disabled={disabled}
            aria-invalid={!!error}
            aria-describedby={hintId}
            onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 12))}
            onBlur={onBlur}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSubmit?.();
            }}
          />
          {error && <Icon name="alert-circle" size={20} className={s.errorIcon} />}
        </div>
        {onScan && <IconButton icon="qr" label="Отсканировать QR-код" outlined onClick={onScan} disabled={disabled} />}
      </div>
      <p id={hintId} className={`t-note ${error ? s.hintError : s.hint}`} role={error ? "alert" : undefined}>
        {error ?? "10 цифр — организация, 12 — ИП"}
      </p>
    </div>
  );
}
