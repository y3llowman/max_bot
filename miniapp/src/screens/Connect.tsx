import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { ActionBar, ActionNote } from "../components/ActionBar";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Icon, type IconName } from "../components/Icon";
import { InnField } from "../components/InnField";
import { APP_NAME, Screen } from "../components/Screen";
import { useToast } from "../components/Toast";
import { checkInn, innError, innFromQr } from "../utils/inn";
import { canScanQr, haptic, scanQr } from "../max/bridge";
import { useSession } from "../session";
import { Splash } from "./Splash";
import s from "./Connect.module.css";

const BENEFITS: { icon: IconName; text: string }[] = [
  { icon: "calendar", text: "Календарь сроков под ваш налоговый режим" },
  { icon: "bell", text: "Напоминания в чате MAX заранее" },
  { icon: "scale", text: "Простыми словами: что, зачем и чем грозит" },
];

/** 02 · Подключение компании и E1 · Ошибка ввода ИНН.
 *  По заметке дизайнера: кнопка неактивна, пока ИНН невалиден; подсказка — отсканировать QR. */
export function Connect() {
  const [inn, setInn] = useState("");
  const [touched, setTouched] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { setCompany } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const changing = (location.state as { change?: boolean } | null)?.change === true;

  const check = checkInn(inn);
  // Ошибку показываем после ухода из поля или когда введено 10+ цифр — не на каждой первой цифре.
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
      if (e instanceof ApiError && e.code === "not_found") {
        setServerError("Не нашли компанию с таким ИНН в реестре ФНС — проверьте цифры");
      } else {
        toast({ text: "Нет связи с ФНС — попробуйте ещё раз", icon: "alert-circle" });
      }
    }
  };

  const scan = async () => {
    if (!canScanQr()) {
      toast({ text: "Сканер QR работает в приложении MAX", icon: "info" });
      return;
    }
    const text = await scanQr();
    if (!text) return;
    const found = innFromQr(text);
    if (found) {
      setInn(found);
      setTouched(true);
      setServerError(null);
    } else {
      toast({ text: "В этом QR-коде нет ИНН", icon: "alert-circle" });
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
        onScan={scan}
        error={error}
      />
      {error ? (
        <div className={s.alert}>
          <Alert tone="info" title="Где взять ИНН">
            В выписке ЕГРЮЛ — или отсканируйте QR-код со счёта или письма из налоговой.
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
