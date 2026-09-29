import s from "./Skeleton.module.css";

interface Props {
  width?: number | string;
  height: number;
  radius?: number;
}

export function Skeleton({ width = "100%", height, radius = 8 }: Props) {
  return <span className={s.skeleton} style={{ width, height, borderRadius: radius }} aria-hidden="true" />;
}

export function CardSkeleton() {
  return (
    <div className={s.card} aria-hidden="true">
      <Skeleton width={40} height={40} radius={12} />
      <div className={s.lines}>
        <Skeleton height={14} radius={7} />
        <Skeleton width={140} height={12} radius={6} />
        <Skeleton width={96} height={20} radius={8} />
      </div>
    </div>
  );
}
