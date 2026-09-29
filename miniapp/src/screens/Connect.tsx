import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { ActionBar, ActionNote } from "../components/ActionBar";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Icon, type IconName } from "../components/Icon";
import { InnField } from "../components/InnField";
import { APP_NAME, Screen } from "../components/Screen";
import { useToast } from "../components/Toast";
import { checkInn, innError } from "../utils/inn";
import { haptic } from "../max/bridge";
import { useSession } from "../session";
import { Splash } from "./Splash";
import s from "./Connect.module.css";

const BENEFITS: { icon: IconName; text: string }[] = [
  { icon: "calendar", text: "Календарь сроков под ваш налоговый режим" },
  { icon: "bell", text: "Напоминания в чате MAX заранее" },
  { icon: "scale", text: "Простыми словами: что, зачем и чем грозит" },
];

export function Connect() {
  const [inn, setInn] = useState("");
  const [touched, setTouched] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { setCompany } = useSession();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const toast = useToast();
  const changing = params.get("change") === "1";

  const check = checkInn(inn);
  const error = serverError ?? (touched || inn.length >= 10 ? innError(check) : null);

  const submit = async () => {
    if (!check.ok || busy) return;
    setBusy(true);
    try {
      const company = await api.connect(inn);
      haptic.success();
      setCompany(company);
      navigate("/tasks", { replace: true });
    } catch (e) {
      setBusy(false);
      haptic.error();
      const code = e instanceof ApiError ? e.code : "server";
      if (code === "not_found") {
        setServerError("Такого ИНН нет в реестре МСП (в демо-версии — в загруженном срезе). Проверьте цифры");
      } else if (code === "conflict") {
        setServerError("Эту компанию уже подключил другой пользователь MAX");
      } else {
        const text = code === "unavailable" ? "Реестр ФНС не отвечает — попробуйте через пару минут"
          : code === "network" ? "Нет соединения — проверьте интернет и попробуйте ещё раз"
          : "Не получилось подключить компанию: ошибка на нашей стороне, попробуйте позже";
        toast({ text, icon: "alert-circle" });
      }
    }
  };

  if (busy) return <Splash />;

  return (
    <Screen
      title={APP_NAME}
      nav={changing ? "back" : "close"}
      gap={0}
      bottom={
        <ActionBar>
          <Button block disabled={!check.ok} onClick={submit}>
            Продолжить
          </Button>
          <ActionNote>Нажимая «Продолжить», вы соглашаетесь с условиями сервиса</ActionNote>
        </ActionBar>
      }
    >
      <h1 className="t-header">Подключите компанию</h1>
      <p className={`t-body ${s.lead}`}>Подберём налоги и сроки по данным ФНС — это займёт около минуты.</p>
      <hr className={s.divider} />
      <InnField
        value={inn}
        onChange={(v) => {
          setInn(v);
          setServerError(null);
        }}
        onBlur={() => inn && setTouched(true)}
        onSubmit={submit}
        error={error}
      />
      {error ? (
        <div className={s.alert}>
          <Alert tone="info" title="Где взять ИНН">
            В свидетельстве о постановке на учёт, в выписке из ЕГРЮЛ или ЕГРИП, в письмах из налоговой.
          </Alert>
        </div>
      ) : (
        <ul className={s.benefits}>
          {BENEFITS.map((b) => (
            <li key={b.icon} className={s.benefit}>
              <span className={s.benefitIcon}>
                <Icon name={b.icon} size={18} />
              </span>
              <span className="t-detail">{b.text}</span>
            </li>
          ))}
        </ul>
      )}
    </Screen>
  );
}
