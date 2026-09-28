import type { Counters } from "../api/types";
import { Icon, type IconName } from "./Icon";
import { Skeleton } from "./Skeleton";
import s from "./StatusTiles.module.css";

const TILES: { key: keyof Counters; label: string; icon: IconName; tone: string }[] = [
  { key: "overdue", label: "Просрочено", icon: "alert-circle", tone: s.danger },
  { key: "soon", label: "Скоро", icon: "clock", tone: s.warning },
  { key: "done", label: "Выполнено", icon: "check-circle", tone: s.success },
];

export function StatusTiles({ counters }: { counters: Counters }) {
  return (
    <div className={s.tiles}>
      {TILES.map((t) => (
        <div key={t.key} className={s.tile}>
          <div className={s.top}>
            <span className="t-header">{counters[t.key]}</span>
            <Icon name={t.icon} size={20} className={t.tone} />
          </div>
          <span className={`t-label ${s.label}`}>{t.label}</span>
        </div>
      ))}
    </div>
  );
}

export function StatusTilesSkeleton() {
  return (
    <div className={s.tiles} aria-hidden="true">
      {TILES.map((t) => (
        <div key={t.key} className={s.skeletonTile}>
          <Skeleton width={28} height={22} radius={6} />
          <Skeleton width={64} height={12} radius={6} />
        </div>
      ))}
    </div>
  );
}
