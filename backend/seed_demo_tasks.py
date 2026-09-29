import asyncio
import sys
from datetime import timedelta

from sqlalchemy import delete

from databases import SessionLocal, init_db
from notifications.models import RadarEvent
from notifications.planner import today_msk

DEMO = [
    (-2, "open", {"title": "Ответ на требование ФНС", "period": "Демо · пояснения к декларации",
                  "what": "Подготовьте пояснения и отправьте их через оператора ЭДО.",
                  "basis": "п. 3 ст. 88 НК РФ · демо-данные", "why": "налоговая прислала требование"}),
    (0, "open", {"title": "Уведомление по НДФЛ", "period": "Демо · КНД 1110355",
                 "what": "Подайте уведомление об исчисленных суммах НДФЛ.",
                 "basis": "п. 9 ст. 58 НК РФ · демо-данные", "why": "у вас есть сотрудники"}),
    (3, "open", {"title": "Декларация по НДС", "period": "Демо · за прошлый квартал",
                 "what": "Сверьте книги покупок и продаж и отправьте декларацию через оператора ЭДО.",
                 "basis": "п. 5 ст. 174 НК РФ · демо-данные", "why": "вы платите НДС"}),
    (6, "open", {"title": "Уплата ЕНП", "period": "Демо · налоги и взносы",
                 "what": "Пополните единый налоговый счёт на сумму начислений.",
                 "basis": "ст. 11.3 НК РФ · демо-данные", "why": "у вас есть начисления к уплате"}),
    (34, "open", {"title": "Уведомление по НДФЛ", "period": "Демо · КНД 1110355",
                  "what": "Подайте уведомление об исчисленных суммах НДФЛ.",
                  "basis": "п. 9 ст. 58 НК РФ · демо-данные", "why": "у вас есть сотрудники"}),
    (-11, "done", {"title": "Аванс по УСН", "period": "Демо · за отчётный период",
                   "what": "Уплатите авансовый платёж по УСН.",
                   "basis": "п. 7 ст. 346.21 НК РФ · демо-данные", "why": "вы на УСН"}),
]


async def main(inn: str) -> None:
    await init_db()
    today = today_msk()
    async with SessionLocal() as db:
        await db.execute(delete(RadarEvent).where(RadarEvent.key.like(f"demo:{inn}:%")))
        for i, (shift, status, payload) in enumerate(DEMO):
            db.add(RadarEvent(inn=inn, type="deadline", kind="once", key=f"demo:{inn}:{i}", source="demo",
                              payload=payload, due=today + timedelta(days=shift), status=status))
        await db.commit()
    print(f"Демо-сроков для ИНН {inn}: {len(DEMO)}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
