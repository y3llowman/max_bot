import { useId, useState } from "react";
import type { TaskSection } from "../api/types";
import { openLink } from "../max/bridge";
import { Icon } from "./Icon";
import s from "./Accordion.module.css";

/** Группа аккордеонов задачи: «Что сделать», «Как отправить», «Правовое обоснование», «Риски при задержке». */
export function Accordion({ sections, defaultOpen = [] }: { sections: TaskSection[]; defaultOpen?: string[] }) {
  const [open, setOpen] = useState<Set<string>>(() => new Set(defaultOpen));
  const baseId = useId();

  const toggle = (id: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className={s.group}>
      {sections.map((sec) => {
        const isOpen = open.has(sec.id);
        const panelId = `${baseId}-${sec.id}`;
        return (
          <div key={sec.id} className={s.item}>
            <button
              type="button"
              className={s.head}
              aria-expanded={isOpen}
              aria-controls={panelId}
              onClick={() => toggle(sec.id)}
            >
              <span className={s.tile}>
                <Icon name={sec.icon} size={22} />
              </span>
              <span className={s.text}>
                <span className="t-body-strong">{sec.title}</span>
                <span className={`t-note ${s.caption}`}>{sec.caption}</span>
              </span>
              <Icon name={isOpen ? "chevron-up" : "chevron-down"} size={20} className={s.chevron} />
            </button>
            {isOpen && (
              <div id={panelId} className={`t-detail ${s.panel}`}>
                {sec.body?.map((p) => (
                  <p key={p}>{p}</p>
                ))}
                {sec.steps && (
                  <ol className={s.steps}>
                    {sec.steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                )}
                {sec.link && (
                  <button type="button" className={`t-detail-strong ${s.link}`} onClick={() => openLink(sec.link!.url)}>
                    {sec.link.label}
                    <Icon name="chevron-right" size={16} />
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
