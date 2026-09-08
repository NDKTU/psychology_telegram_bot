import html
import io
import logging
from typing import Optional

from aiogram import Router, Bot, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    BufferedInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from common.config import settings
from common.database import db

logger = logging.getLogger(__name__)
worker_router = Router()


class WorkerReplyState(StatesGroup):
    waiting_for_reply = State()


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel Reply", callback_data="cancel_worker_reply")]
        ]
    )


@worker_router.message(CommandStart())
async def handle_worker_start(message: Message):
    """Handle /start command in worker bot."""
    user = message.from_user
    if not user:
        return

    # Check if worker provided secret key: /start <secret>
    args = message.text.split(maxsplit=1)
    provided_key = args[1].strip() if len(args) > 1 else ""

    is_group = message.chat.type in ("group", "supergroup")
    already_worker = await db.is_worker(user.id)
    is_chat_target = settings.WORKER_CHAT_ID and (message.chat.id == settings.WORKER_CHAT_ID)

    if already_worker or is_group or is_chat_target or (provided_key and provided_key == settings.WORKER_SECRET_KEY):
        await db.register_worker(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        response_text = (
            "<b>Welcome to the Psychologist / Worker Console!</b> 🩺🌿\n\n"
            "You are authorized as an active specialist.\n\n"
            "<b>How to reply to clients:</b>\n"
            "1. <b>Telegram Reply:</b> Simply hit 'Reply' on any forwarded client message.\n"
            "2. <b>Button:</b> Tap the <i>[ ✍️ Reply to Client ]</i> button on the message.\n"
            "3. <b>Command:</b> Use <code>/reply &lt;client_id&gt; &lt;your message&gt;</code>\n\n"
            "You can reply with text, voice messages, or photos."
            "<b>Specialist Tools:</b>\n"
            "• <code>/unanswered</code> - View all client questions waiting for an answer.\n"
            "• <code>/help</code> - Full command instructions.\n"
            "• <code>/chatid</code> - View current chat/group ID."
        )
    else:
        response_text = (
            "🔒 <b>Worker Authorization Required</b>\n\n"
            "This bot is for authorized specialists only.\n"
            f"Please send <code>/start {settings.WORKER_SECRET_KEY}</code> to activate your worker access."
        )

    await message.answer(response_text)


@worker_router.message(Command("help"))
async def handle_worker_help(message: Message):
    """Display instructions for workers."""
    help_text = (
        "📖 <b>Specialist Help & Instructions</b>\n\n"
        "• <b>Replying to Clients:</b>\n"
        "  - Use Telegram's <b>Reply</b> feature directly on the message.\n"
        "  - Click the <b>✍️ Reply to Client</b> button.\n"
        "  - Type <code>/reply &lt;client_id&gt; &lt;text&gt;</code>\n\n"
        "• <b>Status Tracking & Tools:</b>\n"
        "  - <code>/unanswered</code> - See all client inquiries currently marked as <i>not answered</i>.\n"
        "  - Once you send a reply, the status automatically switches to <b>answered</b> in PostgreSQL.\n\n"
        "• <b>Supported Message Types:</b>\n"
        "  - Text\n"
        "  - Voice messages (sent as voice notes to client)\n"
        "  - Photos & Documents\n\n"
        "• <b>Commands:</b>\n"
        "  - <code>/start</code> - Register / check status\n"
        "  - <code>/unanswered</code> - List pending client questions\n"
        "  - <code>/reply &lt;client_id&gt; &lt;text&gt;</code> - Direct reply\n"
        "  - <code>/chatid</code> - Show current chat ID (useful to configure WORKER_CHAT_ID)\n"
        "  - <code>/chatid</code> - Show current chat ID\n"
    )
    await message.answer(help_text)


@worker_router.message(Command("chatid"))
async def handle_chat_id(message: Message):
    """Show current chat ID so user can easily set WORKER_CHAT_ID in .env."""
    await message.answer(f"🆔 This chat ID is: <code>{message.chat.id}</code>")


@worker_router.message(Command("unanswered"))
async def handle_unanswered(message: Message):
    """List inquiries that are currently marked as 'not_answered'."""
    unanswered = await db.get_unanswered_messages(limit=15)
    if not unanswered:
        await message.answer("🎉 <b>All caught up!</b>\nThere are no unanswered client inquiries at this moment.")
        return

    text = f"📋 <b>Unanswered Client Inquiries ({len(unanswered)})</b>\n\n"
    for i, item in enumerate(unanswered, 1):
        client_name = html.escape(item.get("first_name") or "Anonymous")
        client_id = item.get("client_user_id")
        preview = html.escape(item.get("content") or f"[{item.get('message_type')}]")
        if len(preview) > 60:
            preview = preview[:57] + "..."

        text += (
            f"<b>{i}.</b> 👤 {client_name} (ID: <code>{client_id}</code>)\n"
            f"   💬 <i>\"{preview}\"</i>\n"
            f"   👉 Reply: <code>/reply {client_id} your_answer</code>\n\n"
        )

    await message.answer(text)


@worker_router.callback_query(F.data.startswith("worker_reply:"))
async def handle_reply_callback(callback: CallbackQuery, state: FSMContext):
    """Handle click on 'Reply to Client' button."""
    try:
        _, client_id_str = callback.data.split(":")
        client_id = int(client_id_str)
    except (ValueError, IndexError):
        await callback.answer("Invalid client ID.", show_alert=True)
        return

    await state.update_data(target_client_id=client_id)
    await state.set_state(WorkerReplyState.waiting_for_reply)

    await callback.answer()
    await callback.message.reply(
        f"✍️ <b>Ready to reply to Client</b> (ID: <code>{client_id}</code>)\n\n"
        "Please send your message now (text, voice note, or photo):",
        reply_markup=get_cancel_keyboard()
    )


@worker_router.callback_query(F.data == "cancel_worker_reply")
async def handle_cancel_reply(callback: CallbackQuery, state: FSMContext):
    """Cancel interactive reply."""
    await state.clear()
    await callback.answer("Reply cancelled.")
    await callback.message.edit_text("❌ Reply cancelled.")


@worker_router.message(WorkerReplyState.waiting_for_reply)
async def handle_fsm_reply_message(message: Message, state: FSMContext, client_bot: Bot):
    """Handle the worker's reply when in interactive reply state."""
    data = await state.get_data()
    client_id = data.get("target_client_id")
    if not client_id:
        await state.clear()
        await message.answer("Error: Client ID lost. Please click reply again.")
        return

    answer_text = extract_message_summary(message)
    success = await send_content_to_client(message, client_id, client_bot)
    if success:
        await state.clear()
        await message.reply(f"✅ Your response has been delivered to client (ID: <code>{client_id}</code>).")
        # Mark in database as answered
        await db.mark_message_answered(
            worker_user_id=message.from_user.id if message.from_user else 0,
            answer_text=answer_text,
            client_user_id=client_id
        )
        await message.reply(
            f"✅ Your response has been delivered to client (ID: <code>{client_id}</code>).\n"
            f"📌 Status updated to: <b>Answered</b>"
        )
    else:
        await message.reply("⚠️ Failed to deliver message to client. The client may have blocked the bot.")


@worker_router.message(Command("reply"))
async def handle_reply_command(message: Message, client_bot: Bot):
    """Handle /reply <client_id> <message> command."""
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("Usage: <code>/reply &lt;client_id&gt; &lt;your message&gt;</code>")
        return

    try:
        client_id = int(args[1])
        reply_text = args[2]
    except ValueError:
        await message.reply("Error: client_id must be a valid number.")
        return

    try:
        await client_bot.send_message(
            chat_id=client_id,
            text=f"💬 <b>Response from Specialist:</b>\n\n{html.escape(reply_text)}"
        )
        await message.reply(f"✅ Delivered to client (ID: <code>{client_id}</code>).")
        # Update database status
        await db.mark_message_answered(
            worker_user_id=message.from_user.id if message.from_user else 0,
            answer_text=reply_text,
            client_user_id=client_id
        )
        await message.reply(
            f"✅ Delivered to client (ID: <code>{client_id}</code>).\n"
            f"📌 Status updated to: <b>Answered</b>"
        )
    except Exception as e:
        logger.error(f"Error sending /reply to {client_id}: {e}")
        await message.reply(f"⚠️ Failed to deliver to client: {e}")


@worker_router.message()
async def handle_worker_message_or_reply(message: Message, client_bot: Bot):
    """
    Handle regular messages or Telegram native replies from worker.
    """
    client_id: Optional[int] = None
    db_msg_id: Optional[int] = None

    # 1. Check if this is a Telegram native reply to a message
    if message.reply_to_message:
        mapping = await db.get_client_by_worker_message(
            worker_chat_id=message.chat.id,
            worker_message_id=message.reply_to_message.message_id
        )
        if mapping:
            client_id, _ = mapping
            client_id, _, db_msg_id = mapping

    # 2. Check if there is an active session for this chat if not replied
    if not client_id and message.chat.type == "private":
        client_id = await db.get_active_client_for_worker(message.chat.id)

    if not client_id:
        # Not a reply to any known client message
        if message.chat.type == "private":
            await message.reply(
                "ℹ️ To answer a client, use Telegram's <b>Reply</b> on their message, "
                "or click <b>[ ✍️ Reply to Client ]</b>, or type <code>/reply &lt;id&gt; &lt;text&gt;</code>."
            )
        return

    # Send content to the resolved client
    answer_text = extract_message_summary(message)
    success = await send_content_to_client(message, client_id, client_bot)
    if success:
        await message.reply(f"✅ Delivered to client (ID: <code>{client_id}</code>).")
        # Mark in database as answered
        await db.mark_message_answered(
            worker_user_id=message.from_user.id if message.from_user else 0,
            answer_text=answer_text,
            db_message_id=db_msg_id,
            client_user_id=client_id
        )
        await message.reply(
            f"✅ Delivered to client (ID: <code>{client_id}</code>).\n"
            f"📌 Status updated to: <b>Answered</b>"
        )
    else:
        await message.reply(f"⚠️ Could not deliver message to client (ID: <code>{client_id}</code>).")


def extract_message_summary(message: Message) -> str:
    """Extract brief summary of answer text for database storage."""
    if message.text:
        return message.text
    elif message.voice:
        return f"[Voice Message ({message.voice.duration}s)]"
    elif message.photo:
        return f"[Photo] {message.caption or ''}".strip()
    elif message.document:
        return f"[Document: {message.document.file_name or 'file'}]"
    return "[Media message]"


async def send_content_to_client(message: Message, client_id: int, client_bot: Bot) -> bool:
    """Helper function to forward worker content (text, voice, photo, doc) to client."""
    try:
        prefix = "💬 <b>Response from Specialist:</b>\n\n"

        if message.text:
            await client_bot.send_message(
                chat_id=client_id,
                text=f"{prefix}{html.escape(message.text)}"
            )
            return True

        elif message.voice:
            voice_buf = io.BytesIO()
            await message.bot.download(message.voice.file_id, destination=voice_buf)
            input_file = BufferedInputFile(voice_buf.getvalue(), filename="response.ogg")
            await client_bot.send_voice(
                chat_id=client_id,
                voice=input_file,
                caption="💬 <i>Voice message from Specialist</i>"
            )
            return True

        elif message.photo:
            photo = message.photo[-1]
            photo_buf = io.BytesIO()
            await message.bot.download(photo.file_id, destination=photo_buf)
            input_file = BufferedInputFile(photo_buf.getvalue(), filename="response.jpg")
            caption = prefix
            if message.caption:
                caption += html.escape(message.caption)
            await client_bot.send_photo(
                chat_id=client_id,
                photo=input_file,
                caption=caption
            )
            return True

        elif message.document:
            doc = message.document
            doc_buf = io.BytesIO()
            await message.bot.download(doc.file_id, destination=doc_buf)
            input_file = BufferedInputFile(doc_buf.getvalue(), filename=doc.file_name or "document")
            caption = prefix
            if message.caption:
                caption += html.escape(message.caption)
            await client_bot.send_document(
                chat_id=client_id,
                document=input_file,
                caption=caption
            )
            return True

        else:
            # Fallback for other message types
            await client_bot.send_message(
                chat_id=client_id,
                text=f"{prefix}[Unsupported media format sent by specialist]"
            )
            return True

    except Exception as e:
        logger.error(f"Failed to send content to client {client_id}: {e}")
        return False

