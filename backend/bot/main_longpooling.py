import asyncio
import logging
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__file__)

from message_handler import dp
from bot.client import bot
from databases import init_db
from notifications.worker import build_scheduler, queue_reminders, start_laws


def _log_failure(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.error("Background task failed", exc_info=task.exception())


async def main():
    await init_db()
    scheduler = build_scheduler()
    scheduler.start()
    await queue_reminders()
    laws_task = asyncio.create_task(start_laws())
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
        polling_task.result()
    else:
        await polling_task

    scheduler.shutdown(wait=False)
    await bot.close_session()


if __name__ == "__main__":
    asyncio.run(main())
