import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Company, NotificationSettings } from "../api/types";
import { ContextBar } from "../components/ContextBar";
import { Icon } from "../components/Icon";
import { ListCell, ListGroup } from "../components/List";
import { APP_NAME, Screen } from "../components/Screen";
import { useToast } from "../components/Toast";
import { updatedAt } from "../utils/dates";
import { THEME_LABELS, setThemePref, useThemePref, type ThemePref } from "../utils/theme";
import { useAsync } from "../utils/useAsync";
import { useSession } from "../session";
import s from "./Profile.module.css";

/** «Чат, push» — сводка включённых каналов для строки «Уведомления». */
export function channelsSummary(n: NotificationSettings): string {
  const parts = [n.chat && "чат", n.push && "push", n.email && "почта"].filter(Boolean) as string[];
  if (parts.length === 0) return "Выключены";
  const text = parts.join(", ");
  return text[0].toUpperCase() + text.slice(1);
}

/** 06 · Профиль. */
export function Profile() {
  const { company, setCompany } = useSession();
  const pref = useThemePref();
  const { data: notif } = useAsync(() => api.notifications(), []);
  const [refreshing, setRefreshing] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();

  if (!company) return null;

  const refresh = async () => {
    setRefreshing(true);
    try {
      setCompany(await api.refreshCompany());
      toast({ text: "Данные компании обновлены" });
    } catch {
      toast({ text: "ФНС не отвечает — попробуйте позже", icon: "alert-circle" });
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <Screen title={APP_NAME}>
      <ContextBar />
      <CompanyCard company={company} refreshing={refreshing} onRefresh={refresh} />
      <ListGroup>
        <ListCell
          title="Уведомления"
          value={notif ? channelsSummary(notif) : undefined}
          chevron
          onClick={() => navigate("/notifications")}
        />
        <ListCell
          title="Контрагенты"
          value={String(company.counterparties)}
          chevron
          onClick={() => toast({ text: "Список контрагентов появится в следующей версии", icon: "info" })}
        />
        <ListCell
          title="Тема оформления"
          value={THEME_LABELS[pref]}
          chevron
          select={{
            value: pref,
            options: (Object.keys(THEME_LABELS) as ThemePref[]).map((k) => ({ value: k, label: THEME_LABELS[k] })),
            onChange: (v) => setThemePref(v as ThemePref),
          }}
        />
        <ListCell title="Сменить компанию" chevron onClick={() => navigate("/connect", { state: { change: true } })} />
      </ListGroup>
    </Screen>
  );
}

function CompanyCard({ company, refreshing, onRefresh }: { company: Company; refreshing: boolean; onRefresh: () => void }) {
  const rows: [string, string | undefined][] = [
    ["ОКВЭД", company.okved],
    ["Категория", company.category],
    ["Численность", company.headcount],
    ["Регион", company.region],
    ["ИНН", company.inn],
    ["КПП", company.kpp],
    ["ОГРН", company.ogrn],
  ];
  return (
    <div className={s.card}>
      <div className={s.company}>
        <span className={`t-subheader ${s.avatar}`} aria-hidden="true">
          {company.initials}
        </span>
        <div className={s.info}>
          <span className="t-subheader">{company.fullName}</span>
          <span className="t-note c-secondary">{company.regime}</span>
        </div>
      </div>
      <hr className={s.divider} />
      <dl className={s.rows}>
        {rows
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k} className={s.row}>
              <dt className="t-detail c-secondary">{k}</dt>
              <dd className="t-detail-strong">{v}</dd>
            </div>
          ))}
      </dl>
      <div className={s.source}>
        <Icon name="shield" size={18} className={s.shield} />
        <div className={s.sourceText}>
          <span className="t-note-strong">
            Источник — {company.source.name}
            {company.source.demo ? " · демо-данные" : ""}
          </span>
          <span className="t-note c-secondary">обновлено {updatedAt(company.source.updatedAt)}</span>
        </div>
        <button
          type="button"
          className={s.refresh}
          onClick={onRefresh}
          disabled={refreshing}
          aria-label="Обновить данные из ФНС"
        >
          <Icon name="refresh" size={20} className={refreshing ? s.spin : undefined} />
        </button>
      </div>
    </div>
  );
}
