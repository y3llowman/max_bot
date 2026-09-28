"""Мониторинг новых актов без LLM: publication.pravo.gov.ru → словарные правила → лента.

Конвейер (раз в день, 07:00 МСК, сервис worker):
 1. fetch      /api/Documents за вчера по блокам: президент, ФС, правительство, ФОИВ
               + «subjects» (регионы). Сотни актов в день.
 2. prefilter  по ключевым словам в названии → десятки.
 3. classify   law_rules.classify(): формулировки текста → поля профиля (+ цитаты).
 4. publish    есть сужающий признак и дата вступления → сразу в ленту (auto_publish);
               иначе — карточка модератору (users.is_staff) с найденными цитатами.
               Оставить модерацию дёшево: словарь иногда ловит упоминание «вскользь».
 5. fan-out    regulations.run_feed() по всем профилям.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

import httpx

from radar.law_rules import classify, to_feed_item

API = "http://publication.pravo.gov.ru/api"
BLOCKS = ("president", "assembly", "government", "federal_authorities", "subjects")
AUTO_PUBLISH = True   # False — всё через модерацию

KEYWORDS = ("налог", "страхов", "предпринимател", "малого и среднего", "контрол", "надзор", "проверк",
            "маркировк", "контрольно-кассов", "трудов", "персональн", "лиценз", "закупк", "платформ",
            "самозанят", "бухгалтер", "отчетност", "торгов", "общественного питания", "иностранн")


async def fetch_published(client: httpx.AsyncClient, day: date) -> list[dict]:
    out: list[dict] = []
    for block in BLOCKS:
        page = 1
        while True:
            r = await client.get(f"{API}/Documents", params={
                "Block": block, "PeriodType": "day",
                "Date": day.strftime("%d.%m.%Y"),   # ДД.ММ.ГГГГ — проверено 27.09.2026; ISO API молча игнорирует
                "PageSize": 200, "Index": page})
            r.raise_for_status()
            data = r.json()
            out += [{**it, "block": block} for it in data.get("items", [])]
            if page >= data.get("pagesTotalCount", 1):
                break
            page += 1
    return out


def prefilter(items: list[dict]) -> list[dict]:
    return [it for it in items
            if any(k in (it.get("complexName") or it.get("name") or "").lower().replace("ё", "е") for k in KEYWORDS)]


def moderation_card(item, c, feed_id: int) -> dict:
    lines = "\n".join(f"• <b>{h.label}</b>{' (исключение)' if h.excluded else ''}: «…{h.quote[:160]}…»"
                      for h in c.hits[:8])
    text = (f"🧾 <b>На модерацию</b>\n{item.act}\n\nВступает: "
            f"{item.effective_from.strftime('%d.%m.%Y') if item.effective_from else 'дата не найдена'}\n"
            f"Сужающих признаков: {c.specificity}\n\nНайдено в тексте:\n{lines}")
    kb = [[{"type": "callback", "text": "✅ Опубликовать", "payload": f"feed:{feed_id}:approve"},
           {"type": "callback", "text": "❌ Отклонить", "payload": f"feed:{feed_id}:reject"}],
          [{"type": "link", "text": "Текст акта", "url": item.official_url}]]
    return {"text": text, "format": "html", "attachments": [{"type": "inline_keyboard", "payload": {"buttons": kb}}]}


async def run_daily(get_text, save_item, notify_staff, fan_out, day: date | None = None) -> None:
    """get_text(meta) → str. На портале публикуются электронные образы документов:
    если в PDF нет текстового слоя — OCR (tesseract, rus)."""
    day = day or date.today() - timedelta(days=1)
    async with httpx.AsyncClient(timeout=30) as client:
        for meta in prefilter(await fetch_published(client, day)):
            published = datetime.fromisoformat(meta["publishDateShort"]).date()
            authority = meta.get("complexName", "")   # для subjects там название органа субъекта
            text = await get_text(meta)
            c = classify(meta.get("name", ""), text, published, authority, meta["block"])
            if not c.relevant:
                continue
            item = to_feed_item(meta, c, published, text)
            if not AUTO_PUBLISH:
                item = replace(item, status="pending_review")
            feed_id = await save_item(item, c)
            if item.status == "approved":
                await fan_out(feed_id)
            else:
                await notify_staff(moderation_card(item, c, feed_id))
