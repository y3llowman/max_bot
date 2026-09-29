import { useEffect, useState, type InputHTMLAttributes } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { ProfileForm, ProfileUpdate } from "../api/types";
import { ActionBar } from "../components/ActionBar";
import { Button } from "../components/Button";
import { Toggle } from "../components/Controls";
import { ListCell, ListGroup } from "../components/List";
import { Screen } from "../components/Screen";
import { SectionHeader } from "../components/SectionHeader";
import { Skeleton } from "../components/Skeleton";
import { StateView } from "../components/StateView";
import { useToast } from "../components/Toast";
import { useAsync } from "../utils/useAsync";
import { haptic } from "../max/bridge";
import { useSession } from "../session";
import s from "./ProfileEdit.module.css";

const OKVED = /^\d{2}(\.\d{1,2}){0,2}$/;
const FLAG_VALUES = [
  { value: "yes", label: "Да" },
  { value: "no", label: "Нет" },
  { value: "", label: "Не знаю" },
];

function toUpdate(form: ProfileForm): ProfileUpdate {
  return {
    regime: form.regime ?? null,
    headcount: form.headcount ?? null,
    okved: form.okved,
    region: form.region,
    hasLicenses: form.hasLicenses,
    flags: form.flags,
    patentFrom: form.patentFrom ?? null,
    patentTo: form.patentTo ?? null,
  };
}

const flagValue = (v: boolean | null | undefined) => (v === true ? "yes" : v === false ? "no" : "");

export function ProfileEdit() {
  const { data, error, loading, reload } = useAsync(() => api.profileForm(), []);
  const [draft, setDraft] = useState<ProfileUpdate | null>(null);
  const [saving, setSaving] = useState(false);
  const { setCompany } = useSession();
  const navigate = useNavigate();
  const toast = useToast();

  useEffect(() => {
    if (data) setDraft(toUpdate(data));
  }, [data]);

  const set = <K extends keyof ProfileUpdate>(key: K, value: ProfileUpdate[K]) =>
    setDraft((d) => (d ? { ...d, [key]: value } : d));

  const okvedOk = !!draft && OKVED.test(draft.okved.trim());

  const save = async () => {
    if (!draft || !okvedOk) return;
    setSaving(true);
    try {
      setCompany(await api.saveProfile({ ...draft, okved: draft.okved.trim() }));
    } catch (e) {
      setSaving(false);
      const invalid = e instanceof ApiError && e.code === "invalid";
      toast({
        text: invalid ? "Проверьте срок патента: от 1 дня до 12 месяцев" : "Не получилось сохранить — попробуйте ещё раз",
        icon: "alert-circle",
      });
      return;
    }
    haptic.success();
    navigate("/tasks");
    toast({ text: "Данные сохранены — обязанности пересчитали" });
  };

  if (error) {
    return (
      <Screen title="Данные компании" nav="back">
        <StateView
          tone="danger"
          icon="cloud-off"
          title="Не удалось загрузить данные"
          text="Проверьте интернет и попробуйте ещё раз."
          actions={
            <Button size="m" onClick={reload}>
              Повторить
            </Button>
          }
        />
      </Screen>
    );
  }

  return (
    <Screen
      title="Данные компании"
      nav="back"
      gap={10}
      bottom={
        <ActionBar>
          <Button block onClick={save} disabled={!draft || !okvedOk || saving}>
            Сохранить
          </Button>
        </ActionBar>
      }
    >
      {loading || !data || !draft ? (
        <>
          <Skeleton width={140} height={16} />
          <Skeleton height={144} radius={16} />
          <Skeleton width={110} height={16} />
          <Skeleton height={192} radius={16} />
        </>
      ) : (
        <>
          <p className="t-detail c-secondary">
            Нашли в открытых реестрах ФНС. Если что-то не так — поправьте: от этого зависят обязанности и законы, о
            которых пишет бот.
          </p>

          <SectionHeader title="Налоги и сотрудники" />
          <ListGroup>
            <ListCell
              title="Режим налогообложения"
              caption={data.options.regimes.find((o) => o.value === draft.regime)?.label ?? "Не указан — выберите"}
              chevron
              select={{
                value: draft.regime ?? "",
                options: [{ value: "", label: "Не указан" }, ...data.options.regimes],
                onChange: (v) => set("regime", v || null),
              }}
            />
            {draft.regime === "psn" && (
              <>
                <InputCell title="Патент действует с" type="date" value={draft.patentFrom ?? ""}
                  onChange={(e) => set("patentFrom", e.target.value || null)} />
                <InputCell title="по" type="date" value={draft.patentTo ?? ""}
                  onChange={(e) => set("patentTo", e.target.value || null)} />
              </>
            )}
            <ListCell
              title="Численность"
              caption={
                data.options.headcounts.find((o) => o.value === draft.headcount)?.label ??
                (data.registryHeadcount != null ? `${data.registryHeadcount} чел. — по реестру ФНС` : "Не указана — выберите")
              }
              chevron
              select={{
                value: draft.headcount ?? "",
                options: [
                  { value: "", label: data.registryHeadcount != null ? `Как в реестре ФНС (${data.registryHeadcount} чел.)` : "Не указана" },
                  ...data.options.headcounts,
                ],
                onChange: (v) => set("headcount", v || null),
              }}
            />
          </ListGroup>

          <SectionHeader title="Деятельность" />
          <ListGroup>
            <InputCell
              title="Основной ОКВЭД"
              caption={okvedOk ? `В реестре: ${data.registryOkved}` : "Код вида 56.10"}
              error={!okvedOk}
              inputMode="decimal"
              value={draft.okved}
              onChange={(e) => set("okved", e.target.value.replace(/[^\d.]/g, "").slice(0, 8))}
            />
            <ListCell
              title="Регион"
              caption={data.options.regions.find((o) => o.value === draft.region)?.label ?? data.registryRegion}
              chevron
              select={{ value: draft.region, options: data.options.regions, onChange: (v) => set("region", v) }}
            />
            <ListCell
              title="Есть лицензии"
              role="switch"
              checked={draft.hasLicenses}
              onClick={() => set("hasLicenses", !draft.hasLicenses)}
              trail={<Toggle checked={draft.hasLicenses} />}
            />
          </ListGroup>

          <SectionHeader title="Для ленты законов" />
          <ListGroup>
            {data.options.flags.map((flag) => (
              <ListCell
                key={flag.value}
                title={flag.label}
                value={FLAG_VALUES.find((o) => o.value === flagValue(draft.flags[flag.value]))?.label}
                chevron
                select={{
                  value: flagValue(draft.flags[flag.value]),
                  options: FLAG_VALUES,
                  onChange: (v) => set("flags", { ...draft.flags, [flag.value]: v === "yes" ? true : v === "no" ? false : null }),
                }}
              />
            ))}
          </ListGroup>
          <p className="t-note c-secondary">«Не знаю» — бот спросит, когда выйдет первый закон на эту тему.</p>
        </>
      )}
    </Screen>
  );
}

function InputCell({ title, caption, error, ...input }: { title: string; caption?: string; error?: boolean } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={s.cell}>
      <span className={s.text}>
        <span className="t-body">{title}</span>
        {caption && <span className={`t-note ${error ? s.error : s.caption}`}>{caption}</span>}
      </span>
      <input className={`t-body ${s.input} ${error ? s.inputError : ""}`} aria-invalid={error} {...input} />
    </label>
  );
}
