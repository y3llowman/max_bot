import { useNavigate } from "react-router-dom";
import { openChat } from "../max/bridge";
import { useSession } from "../session";
import { Icon } from "./Icon";
import s from "./ContextBar.module.css";

/** Context Bar — компания, уведомления и «В чат MAX». По киту: только на экранах верхнего уровня. */
export function ContextBar({ unread = false }: { unread?: boolean }) {
  const navigate = useNavigate();
  const { company } = useSession();

  return (
    <div className={s.bar}>
      <button type="button" className={s.company} onClick={() => navigate("/profile")}>
        <span className={`t-body-strong ${s.name}`}>{company?.name ?? ""}</span>
        <Icon name="chevron-down" size={18} className={s.chevron} />
      </button>
      <button
        type="button"
        className={s.bell}
        onClick={() => navigate("/notifications")}
        aria-label={unread ? "Уведомления, есть новые" : "Уведомления"}
      >
        <Icon name="bell" size={24} />
        {unread && <span className={s.unread} aria-hidden="true" />}
      </button>
      <button type="button" className={s.pill} onClick={openChat}>
        <Icon name="chat-back" size={18} />
        <span className="t-action-s">В чат MAX</span>
      </button>
    </div>
  );
}
