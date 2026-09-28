import asyncio
import logging
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# backend/ (родитель этой папки) должен быть в sys.path — оттуда бот
# импортирует databases, data_fetching, notifications и т.д.
BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__file__)

# message_handler владеет dp (создаёт Dispatcher и регистрирует обработчики).
# Импортируем dp отсюда, а не наоборот: этот файл всегда запускается как
# скрипт (__name__ == "__main__"), и обратный импорт "from main_longpooling
# import dp" внутри message_handler.py заставил бы Python загрузить этот
# файл ВТОРОЙ раз под именем "main_longpooling" (это уже не тот же модуль,
# что "__main__") - со своим отдельным Dispatcher, на который и регистрировались
# бы все обработчики, пока реальный polling шёл бы на пустом dp.
from message_handler import dp  # noqa: E402
from bot.client import bot  # noqa: E402
from databases import init_db  # noqa: E402
from notifications.worker import build_scheduler, queue_reminders, start_laws  # noqa: E402


def _log_failure(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.error("Background task failed", exc_info=task.exception())


async def main():
    await init_db()
    # планировщик радара живёт в процессе бота: бот один, задачи не задвоятся
    scheduler = build_scheduler()
    scheduler.start()
    await queue_reminders()  # если бот лежал в 09:00 — напоминания на сегодня всё равно уйдут
    # акты pravo.gov.ru: при первом запуске — месяц без рассылки, иначе догнать 07:00; минуты — в фоне
    laws_task = asyncio.create_task(start_laws())  # ссылка живёт, пока работает main()
    laws_task.add_done_callback(_log_failure)
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def request_stop() -> None:
        logger.info("Получен сигнал остановки, завершаю polling...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            # Windows: event loop не поддерживает add_signal_handler
            signal.signal(sig, lambda *_args: request_stop())

    polling_task = asyncio.create_task(dp.start_polling(bot, skip_updates=True))
    stop_task = asyncio.create_task(stop_event.wait())

    await asyncio.wait(
        {polling_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
    )

    if not stop_task.done():
        stop_task.cancel()

    await dp.stop_polling()

    if polling_task.done():
        polling_task.result()  # пробросить исключение, если polling упал сам
    else:
        await polling_task

    scheduler.shutdown(wait=False)
    await bot.close_session()


if __name__ == "__main__":
    asyncio.run(main())
