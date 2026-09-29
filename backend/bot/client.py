from maxapi import Bot
from maxapi.enums.parse_mode import ParseMode
from maxapi.types.attachments.attachment import ButtonsPayload

from core.env import ENV

bot = Bot(token=ENV.MAX_BOT_TOKEN.get_secret_value())

_bot_app: dict | None = None


async def bot_app() -> dict:
    global _bot_app
    if _bot_app is None:
        me = await bot.get_me()
        if not me.username:
            raise RuntimeError("У бота нет публичного имени (username) — кнопка open_app без него не работает")
        _bot_app = {"web_app": me.username, "contact_id": me.user_id}
    return _bot_app


async def send_html(max_user_id: int, text: str, keyboard: dict | None = None) -> str | None:
    attachments = [ButtonsPayload.model_validate(keyboard["payload"]).pack()] if keyboard else None
    sent = await bot.send_message(user_id=max_user_id, text=text, format=ParseMode.HTML,
                                  attachments=attachments)
    return sent.message.body.mid if sent else None
