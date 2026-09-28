import { Link } from "react-router-dom";
import type { Task } from "../api/types";
import { dueLabel } from "../utils/tasks";
import { StatusChip } from "./Chip";
import { Icon } from "./Icon";
import s from "./TaskCard.module.css";

export function TaskCard({ task }: { task: Task }) {
  return (
    <Link to={`/task/${task.id}`} className={s.card}>
      <span className={s.icon}>
        <Icon name="file" size={22} />
      </span>
      <span className={s.body}>
        <span className={`t-body-strong ${s.title}`}>{task.title}</span>
        <span className={`t-detail ${s.subtitle}`}>{task.subtitle}</span>
        <span className={s.status}>
          <StatusChip status={task.status} />
          <span className="t-note-strong">{dueLabel(task)}</span>
        </span>
      </span>
      <Icon name="chevron-right" size={20} className={s.chevron} />
    </Link>
  );
}
