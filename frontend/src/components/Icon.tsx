import { icons, type IconName } from "./icons";

export type { IconName };

interface Props {
  name: IconName;
  /** Размеры из макетов: 18, 20, 22, 24 — обводка масштабируется вместе с иконкой, как в Фигме. */
  size?: number;
  className?: string;
  /** Подпись для скринридера; без неё иконка декоративная. */
  label?: string;
}

export function Icon({ name, size = 24, className, label }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
      dangerouslySetInnerHTML={{ __html: icons[name] }}
    />
  );
}
