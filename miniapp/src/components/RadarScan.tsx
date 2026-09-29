import { updatedAt } from "../utils/dates";
import { Button } from "./Button";
import s from "./RadarScan.module.css";

interface Props {
  scanning: boolean;
  checkedAt?: string;
  onScan: () => void;
}

export function RadarScan({ scanning, checkedAt, onScan }: Props) {
  return (
    <div className={s.card}>
      <div className={s.head}>
        <div className={`${s.radar} ${scanning ? s.scanning : ""}`} aria-hidden="true">
          <span className={s.sweep} />
          <span className={s.blip} />
        </div>
        <div className={s.text} role="status">
          <span className="t-body-strong">{scanning ? "Сканируем реестры ФНС…" : "Радар включён"}</span>
          <span className="t-note c-secondary">
            {scanning
              ? "Реестр МСП и выписка ЕГРЮЛ"
              : checkedAt
                ? `Проверено ${updatedAt(checkedAt)}. Следующая проверка — ночью`
                : "Проверяем реестры каждую ночь"}
          </span>
        </div>
      </div>
      <Button size="m" variant="secondary" block onClick={onScan} disabled={scanning}>
        {scanning ? "Сканируем…" : "Просканировать сейчас"}
      </Button>
    </div>
  );
}
