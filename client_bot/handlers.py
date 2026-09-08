import html
import io
import logging
from typing import List
from aiogram import Router, Bot, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from common.config import settings
from common.database import db

logger = logging.getLogger(__name__)
client_router = Router()


def get_worker_reply_keyboard(client_id: int) -> InlineKeyboardMarkup:
    """Generate keyboard for worker to easily reply."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Mijozga javob berish",
                    callback_data=f"worker_reply:{client_id}"
                )
            ]
        ]
    )


async def get_worker_targets() -> List[int]:
    """Get list of active logged-in workers to deliver client inquiries to."""
    workers = await db.get_active_workers()
    targets = list(workers)
    if settings.WORKER_CHAT_ID and settings.WORKER_CHAT_ID != 0 and settings.WORKER_CHAT_ID not in targets:
        targets.append(settings.WORKER_CHAT_ID)
    return targets


@client_router.message(CommandStart())
async def handle_start(message: Message):
    """Handle /start command from client in Uzbek."""
    user = message.from_user
    if user:
        await db.upsert_client(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

    welcome_text = (
        "<b>Xush kelibsiz!</b> 🌿\n\n"
        "Bu psixologik yordam va qo'llab-quvvatlash uchun xavfsiz hamda maxfiy maskan.\n"
        "Bu yerda o'z his-tuyg'ularingiz, fikrlaringiz yoki savollaringizni istalgan vaqtda yozib qoldirishingiz mumkin.\n\n"
        "Mutaxassislarimiz xabaringizni ko'rib chiqib, imkon qadar tezroq javob berishadi. "
        "Matnli yoki ovozli xabar ko'rinishida yuborishingiz mumkin."
    )
    await message.answer(welcome_text)


@client_router.message(F.text)
async def handle_client_text(message: Message, worker_bot: Bot):
    """Handle incoming text messages from client."""
    user = message.from_user
    if not user:
        return

    await db.upsert_client(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    db_msg_id = await db.save_client_message(
        client_user_id=user.id,
        client_message_id=message.message_id,
        message_type="text",
        content=message.text
    )

    targets = await get_worker_targets()
    if not targets:
        logger.warning("Hozirda tizimga kirgan mutaxassislar mavjud emas!")

    username_str = f"@{user.username}" if user.username else "Username yo'q"
    full_name = html.escape(user.full_name or "Anonim")

    worker_msg_text = (
        f"📩 <b>Mijozdan yangi xabar</b>\n"
        f"👤 <b>Ism:</b> {full_name}\n"
        f"🆔 <b>Mijoz ID:</b> <code>{user.id}</code>\n"
        f"🔗 <b>Username:</b> {username_str}\n"
        f"📌 <b>Holat:</b> ⏳ <i>Javob berilmagan</i>\n\n"
        f"💬 <b>Xabar:</b>\n{html.escape(message.text)}"
    )

    kb = get_worker_reply_keyboard(user.id)

    for chat_id in targets:
        try:
            sent_msg = await worker_bot.send_message(
                chat_id=chat_id,
                text=worker_msg_text,
                reply_markup=kb
            )
            await db.link_worker_message(
                db_message_id=db_msg_id,
                worker_chat_id=chat_id,
                worker_message_id=sent_msg.message_id,
                client_user_id=user.id,
                client_message_id=message.message_id
            )
        except Exception as e:
            logger.error(f"Failed to deliver message to worker chat {chat_id}: {e}")

    await message.answer("✅ Xabaringiz qabul qilindi. Tez orada mutaxassis sizga javob beradi.")


@client_router.message(F.voice)
async def handle_client_voice(message: Message, worker_bot: Bot):
    """Handle voice messages from client."""
    user = message.from_user
    if not user or not message.voice:
        return

    await db.upsert_client(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    db_msg_id = await db.save_client_message(
        client_user_id=user.id,
        client_message_id=message.message_id,
        message_type="voice",
        content=f"Ovozli xabar ({message.voice.duration}s)"
    )

    targets = await get_worker_targets()
    full_name = html.escape(user.full_name or "Anonim")
    username_str = f"@{user.username}" if user.username else "Username yo'q"

    caption = (
        f"🎙 <b>Mijozdan yangi ovozli xabar</b>\n"
        f"👤 <b>Ism:</b> {full_name}\n"
        f"🆔 <b>Mijoz ID:</b> <code>{user.id}</code>\n"
        f"🔗 <b>Username:</b> {username_str}\n"
        f"⏱ <b>Davomiyligi:</b> {message.voice.duration} soniya\n"
        f"📌 <b>Holat:</b> ⏳ <i>Javob berilmagan</i>"
    )

    voice_buffer = io.BytesIO()
    await message.bot.download(message.voice.file_id, destination=voice_buffer)
    voice_bytes = voice_buffer.getvalue()

    kb = get_worker_reply_keyboard(user.id)

    for chat_id in targets:
        try:
            input_file = BufferedInputFile(voice_bytes, filename="voice.ogg")
            sent_msg = await worker_bot.send_voice(
                chat_id=chat_id,
                voice=input_file,
                caption=caption,
                reply_markup=kb
            )
            await db.link_worker_message(
                db_message_id=db_msg_id,
                worker_chat_id=chat_id,
                worker_message_id=sent_msg.message_id,
                client_user_id=user.id,
                client_message_id=message.message_id
            )
        except Exception as e:
            logger.error(f"Failed to forward voice to worker chat {chat_id}: {e}")

    await message.answer("✅ Ovozli xabaringiz qabul qilindi. Mutaxassis eshitib ko'rib, javob beradi.")


@client_router.message(F.photo)
async def handle_client_photo(message: Message, worker_bot: Bot):
    """Handle photo messages from client."""
    user = message.from_user
    if not user or not message.photo:
        return

    await db.upsert_client(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    db_msg_id = await db.save_client_message(
        client_user_id=user.id,
        client_message_id=message.message_id,
        message_type="photo",
        content=message.caption or "Rasm"
    )

    targets = await get_worker_targets()
    full_name = html.escape(user.full_name or "Anonim")
    username_str = f"@{user.username}" if user.username else "Username yo'q"

    caption = (
        f"📷 <b>Mijozdan yangi rasm</b>\n"
        f"👤 <b>Ism:</b> {full_name}\n"
        f"🆔 <b>Mijoz ID:</b> <code>{user.id}</code>\n"
        f"🔗 <b>Username:</b> {username_str}\n"
        f"📌 <b>Holat:</b> ⏳ <i>Javob berilmagan</i>"
    )
    if message.caption:
        caption += f"\n\n💬 <b>Izoh:</b>\n{html.escape(message.caption)}"

    kb = get_worker_reply_keyboard(user.id)

    photo = message.photo[-1]
    photo_buffer = io.BytesIO()
    await message.bot.download(photo.file_id, destination=photo_buffer)
    photo_bytes = photo_buffer.getvalue()

    for chat_id in targets:
        try:
            input_file = BufferedInputFile(photo_bytes, filename="photo.jpg")
            sent_msg = await worker_bot.send_photo(
                chat_id=chat_id,
                photo=input_file,
                caption=caption,
                reply_markup=kb
            )
            await db.link_worker_message(
                db_message_id=db_msg_id,
                worker_chat_id=chat_id,
                worker_message_id=sent_msg.message_id,
                client_user_id=user.id,
                client_message_id=message.message_id
            )
        except Exception as e:
            logger.error(f"Failed to forward photo to worker chat {chat_id}: {e}")

    await message.answer("✅ Rasmingiz qabul qilindi. Mutaxassis ko'rib chiqadi.")


@client_router.message(F.document)
async def handle_client_document(message: Message, worker_bot: Bot):
    """Handle documents from client."""
    user = message.from_user
    if not user or not message.document:
        return

    await db.upsert_client(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    doc = message.document
    db_msg_id = await db.save_client_message(
        client_user_id=user.id,
        client_message_id=message.message_id,
        message_type="document",
        content=f"Hujjat: {doc.file_name or 'nomsiz'}"
    )

    targets = await get_worker_targets()
    full_name = html.escape(user.full_name or "Anonim")
    username_str = f"@{user.username}" if user.username else "Username yo'q"

    caption = (
        f"📄 <b>Mijozdan yangi hujjat</b>\n"
        f"👤 <b>Ism:</b> {full_name}\n"
        f"🆔 <b>Mijoz ID:</b> <code>{user.id}</code>\n"
        f"🔗 <b>Username:</b> {username_str}\n"
        f"📁 <b>Fayl:</b> {doc.file_name or 'nomsiz'}\n"
        f"📌 <b>Holat:</b> ⏳ <i>Javob berilmagan</i>"
    )
    if message.caption:
        caption += f"\n\n💬 <b>Izoh:</b>\n{html.escape(message.caption)}"

    kb = get_worker_reply_keyboard(user.id)

    doc_buffer = io.BytesIO()
    await message.bot.download(doc.file_id, destination=doc_buffer)
    doc_bytes = doc_buffer.getvalue()

    for chat_id in targets:
        try:
            input_file = BufferedInputFile(doc_bytes, filename=doc.file_name or "document")
            sent_msg = await worker_bot.send_document(
                chat_id=chat_id,
                document=input_file,
                caption=caption,
                reply_markup=kb
            )
            await db.link_worker_message(
                db_message_id=db_msg_id,
                worker_chat_id=chat_id,
                worker_message_id=sent_msg.message_id,
                client_user_id=user.id,
                client_message_id=message.message_id
            )
        except Exception as e:
            logger.error(f"Failed to forward document to worker chat {chat_id}: {e}")

    await message.answer("✅ Hujjatingiz qabul qilindi.")
