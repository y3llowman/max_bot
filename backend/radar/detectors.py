from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date

from .catalog import ON_RESOLVE
from .render import as_date, fio


@dataclass
class Draft:
    type: str
    key: str
    payload: dict = field(default_factory=dict)
    due: date | None = None


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _is_foreign(director: dict | None) -> bool:
    citizenship = (director or {}).get("citizenship") or ""
    return bool(citizenship) and "росси" not in citizenship.lower()


def _person(p: dict | None) -> str | None:
    if not p:
        return None
    return p.get("full_name") or fio(" ".join(filter(None, (p.get("surname"), p.get("name"), p.get("patronymic"))))) or None


def _founders(extract: dict) -> str | None:
    parts = [f"{_person(f)} ({f['share_percent']:g}%)" if f.get("share_percent") is not None else _person(f)
             for f in extract.get("founders") or []]
    return "; ".join(parts) or None


UNRELIABLE_ABOUT = {
    "Место нахождения и адрес юридического лица": "адрес",
    "Сведения о лице, имеющем право без доверенности действовать от имени юридического лица": "руководитель",
    "Сведения об участниках / учредителях юридического лица": "участники",
}


def egrul_conditions(inn: str, cur: dict, today: date) -> list[Draft]:
    drafts = []

    unreliable = [n for n in cur.get("notes") or [] if "недостовер" in n["text"].lower()]
    if unreliable:
        dates = [as_date(n["date"]) for n in unreliable if n.get("date")]
        mark = min(dates) if dates else None
        exclusion = add_months(mark, 6) if mark else None
        about = list(dict.fromkeys(UNRELIABLE_ABOUT.get(n["section"], n["section"].lower()) for n in unreliable))
        drafts.append(Draft("egrul.unreliable", key=f"egrul.unreliable:{inn}", due=exclusion, payload={
            "note": unreliable[0]["text"], "about": about,
            "mark_date": mark and mark.isoformat(), "exclusion_possible_from": exclusion and exclusion.isoformat(),
            "title": "Недостоверные сведения в ЕГРЮЛ", "period": "Недостоверно: " + ", ".join(about),
            "why": "ФНС внесла в ЕГРЮЛ отметку о недостоверности сведений: " + ", ".join(about),
            "what": "Подайте исправленные или подтверждённые сведения по форме Р13014.",
            "basis": "п. 5 ст. 21.1 закона № 129-ФЗ"}))

    end = as_date(cur.get("director_disqualification_end"))
    if end and end >= today:
        director = cur.get("director") or {}
        drafts.append(Draft("egrul.director_disqualified", key=f"egrul.disqualified:{inn}:{end}", payload={
            "director": {"fio": _person(director), "citizenship": director.get("citizenship")},
            "start": cur.get("director_disqualification_start"), "end": cur["director_disqualification_end"],
            "court_date": cur.get("director_disqualification_court_date")}))

    status = cur.get("status")
    if status:
        since = as_date(cur.get("status_date"))
        payload, due = {"note": status, "since": cur.get("status_date"), "objection_due": None}, None
        if "исключ" in status.lower() and since:
            due = add_months(since, 3)
            payload |= {"objection_due": due.isoformat(), "title": "Возражение против исключения из ЕГРЮЛ",
                        "period": f"Решение ФНС от {since:%d.%m.%Y}", "why": "ФНС решила исключить компанию из ЕГРЮЛ",
                        "what": "Если компания работает, подайте в ИФНС заявление по форме Р38001 — тогда её не исключат.",
                        "basis": "п. 3–4 ст. 21.1 закона № 129-ФЗ"}
        drafts.append(Draft("egrul.termination", key=f"egrul.termination:{inn}:{cur.get('status_date')}",
                            payload=payload, due=due))
    return drafts


CHANGE_FIELDS = {
    "director": ("руководитель", lambda e: _person(e.get("director"))),
    "founders": ("участники", _founders),
    "address": ("адрес", lambda e: e.get("address")),
    "tax_authority": ("налоговая инспекция", lambda e: e.get("tax_authority_name")),
}


def egrul_changes(inn: str, prev: dict | None, cur: dict, today: date) -> list[Draft]:
    if not prev:
        return []
    drafts = []
    for name, (title, get) in CHANGE_FIELDS.items():
        old, new = get(prev), get(cur)
        if old is not None and old != new:
            drafts.append(Draft("egrul.changed", key=f"egrul.changed:{inn}:{name}:{today}",
                                payload={"field": name, "field_title": title, "old": old, "new": new}))
    director = cur.get("director")
    if any(d.payload["field"] == "director" for d in drafts) and _is_foreign(director):
        name = _person(director)
        drafts.append(Draft("mvd.foreign_director", key=f"mvd.foreign_director:{inn}:{name}", due=today, payload={
            "director": {"fio": name, "citizenship": director["citizenship"]},
            "title": "Уведомление МВД о трудовом договоре с иностранцем", "period": f"Новый руководитель: {name}",
            "why": f"руководитель — иностранный гражданин ({director['citizenship']})",
            "what": "Подайте в МВД уведомление о заключении трудового договора с иностранным гражданином.",
            "basis": "п. 8 ст. 13 закона № 115-ФЗ"}))
    return drafts


KNM_ACCUSATIVE = {"Выездная проверка": "выездную проверку", "Документарная проверка": "документарную проверку",
                  "Контрольная закупка": "контрольную закупку", "Мониторинговая закупка": "мониторинговую закупку"}
KNM_CANCELLED = ("Отменено", "Не может быть проведено")


def inspection_events(inn: str, knms: list[dict], today: date) -> tuple[list[Draft], list[str]]:
    drafts, cancelled = [], []
    for k in knms:
        key = f"knm:{k['erpid']}"
        if k["status"] in KNM_CANCELLED:
            cancelled.append(key)
        elif k["status_key"] == "REMARK":
            drafts.append(Draft("inspection.warning", key=f"knm.warning:{k['erpid']}", payload={
                "authority": k["authority"], "control": k["control"], "date": k["start"], "text": k["warning"] or ""}))
        elif k["status_key"] == "TYPE_WAITING_CARRY_OUT" and k["start"] and as_date(k["start"]) >= today:
            start, stop = as_date(k["start"]), as_date(k["stop"] or k["start"])
            visit = k["classification"] == "ПМ"
            drafts.append(Draft("inspection.planned", key=key, due=start, payload={
                "classification": k["classification"], "type_name": k["type_name"],
                "authority": k["authority"], "control": k["control"], "start": k["start"],
                "kind": KNM_ACCUSATIVE.get(k["kind"], (k["kind"] or "мероприятие").lower()),
                "title": k["kind"] or "Контрольное мероприятие", "period": f"{start:%d.%m}–{stop:%d.%m.%Y}",
                "why": f"мероприятие внесено в ЕРКНМ по вашему ИНН ({k['control']})",
                "what": ("Подготовьтесь к беседе с инспектором: по итогам профилактического визита предписания не выдаются."
                         if visit else "Изучите проверочные листы по этому виду контроля и подготовьте документы до начала."),
                "basis": "ст. 52 закона № 248-ФЗ" if visit else "закон № 248-ФЗ «О государственном контроле»"}))
    return drafts, cancelled


def reconcile_conditions(open_keys: dict[str, str], drafts: list[Draft]) -> list[str]:
    seen = {d.key for d in drafts}
    return [key for key in open_keys if key not in seen]


def resolutions(closed: list, today: date) -> list[Draft]:
    drafts = []
    for event in closed:
        resolved_type = ON_RESOLVE.get(event.type)
        if resolved_type is None:
            continue
        if event.type == "egrul.director_disqualified" and as_date(event.payload["end"]) > today:
            continue
        drafts.append(Draft(resolved_type, key=f"{event.key}:resolved:{today}", payload=event.payload))
    return drafts


MSP_CATEGORY_RU = {1: "микропредприятие", 2: "малое предприятие", 3: "среднее предприятие"}
MSP_CONDITIONS = ("msp.not_found", "msp.excluded")


def msp_changes(inn: str, prev: dict | None, cur: dict | None, today: date) -> list[Draft]:
    if cur is None:
        return [Draft("msp.not_found", key=f"msp.not_found:{inn}", payload={})]
    if cur.get("date_excluded"):
        return [Draft("msp.excluded", key=f"msp.excluded:{inn}", payload={"date_excluded": cur["date_excluded"]})]
    if not prev or prev.get("category") == cur["category"] or not prev.get("category"):
        return []
    old, new = prev["category"], cur["category"]
    payload = {"old": MSP_CATEGORY_RU.get(old, "нет данных"), "new": MSP_CATEGORY_RU.get(new, "нет данных"),
               "lost_micro": old == 1 and new > 1}
    due = None
    if payload["lost_micro"]:
        due = add_months(today, 4)
        payload |= {"lna_due": due.isoformat(), "title": "Локальные нормативные акты", "period": "После смены категории МСП",
                    "what": "Утвердите правила внутреннего трудового распорядка, положение об оплате труда и другие ЛНА.",
                    "why": f"вы больше не микропредприятие: теперь {payload['new']}", "basis": "ст. 309.2 ТК РФ"}
    return [Draft("msp.category_changed", key=f"msp.category:{inn}:{old}-{new}:{today}", payload=payload, due=due)]
