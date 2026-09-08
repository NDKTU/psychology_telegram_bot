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


class WorkerLoginState(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()


class WorkerReplyState(StatesGroup):
    waiting_for_reply = State()


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel Reply", callback_data="cancel_worker_reply")]
        ]
    )


@worker_router.message(CommandStart())
async def handle_worker_start(message: Message, state: FSMContext):
    """Handle /start in worker bot with login check."""
    user = message.from_user
    if not user:
        return

    # Check if already logged in as worker
    already_worker = await db.is_worker(user.id)
    if already_worker:
        await message.answer(
            f"🌿 <b>Welcome back, {html.escape(user.first_name or 'Specialist')}!</b> 🩺\n\n"
            "You are logged in and active. You will receive all client inquiries here.\n\n"
            "<b>Commands:</b>\n"
            "• <code>/unanswered</code> - View all client inquiries waiting for a response\n"
            "• <code>/reply &lt;client_id&gt; &lt;text&gt;</code> - Answer client by ID\n"
            "• <code>/logout</code> - Sign out of your shift\n"
            "• <code>/help</code> - Full instructions"
        )
        return

    # Prompt for admin login
    await state.set_state(WorkerLoginState.waiting_for_login)
    await message.answer(
        "🔒 <b>Specialist / Admin Authorization Required</b>\n\n"
        "Please enter your <b>Admin Login</b> to access the worker console:"
    )


@worker_router.message(WorkerLoginState.waiting_for_login)
async def handle_login_input(message: Message, state: FSMContext):
    """Receive login username."""
    login_text = message.text.strip() if message.text else ""
    await state.update_data(worker_login=login_text)
    await state.set_state(WorkerLoginState.waiting_for_password)
    await message.answer("🔑 Enter your <b>Password</b>:")


@worker_router.message(WorkerLoginState.waiting_for_password)
async def handle_password_input(message: Message, state: FSMContext):
    """Receive password and authenticate against config credentials."""
    user = message.from_user
    if not user:
        await state.clear()
        return

    data = await state.get_data()
    login_entered = data.get("worker_login", "")
    password_entered = message.text.strip() if message.text else ""

    await state.clear()

    # Check credentials
    if login_entered == settings.ADMIN_LOGIN and password_entered == settings.ADMIN_PASSWORD:
        await db.register_worker(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        await message.answer(
            "✅ <b>Access Granted! Welcome to the Specialist Console.</b> 🩺🌿\n\n"
            "You are now authenticated. All incoming client inquiries from the client bot "
            "will be forwarded directly to your chat.\n\n"
            "<b>Quick tips:</b>\n"
            "• To reply to a client: use Telegram's <b>Reply</b> feature or tap <b>[ ✍️ Reply to Client ]</b>.\n"
            "• Type <code>/unanswered</code> anytime to view pending questions."
        )
    else:
        await message.answer(
            "❌ <b>Incorrect Login or Password!</b> Access denied.\n\n"
            "Please send <code>/start</code> or <code>/login</code> to try again."
        )


@worker_router.message(Command("login"))
async def handle_login_command(message: Message, state: FSMContext):
    """Handle /login or /login <username> <password>."""
    user = message.from_user
    if not user:
        return

    args = message.text.split()
    if len(args) == 3:
        login_val, pass_val = args[1].strip(), args[2].strip()
        if login_val == settings.ADMIN_LOGIN and pass_val == settings.ADMIN_PASSWORD:
            await db.register_worker(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name
            )
            await message.answer(
                "✅ <b>Access Granted!</b> You are logged in as an active specialist."
            )
            return
        else:
            await message.answer("❌ <b>Incorrect Login or Password!</b>")
            return

    # Interactive login fallback
    await state.set_state(WorkerLoginState.waiting_for_login)
    await message.answer("🔒 Please enter your <b>Admin Login</b>:")


@worker_router.message(Command("logout"))
async def handle_worker_logout(message: Message):
    """Log out a specialist from receiving messages."""
    user = message.from_user
    if user:
        await db.logout_worker(user.id)
        await message.answer(
            "👋 <b>Logged Out Successfully.</b>\n"
            "You will not receive client messages until you log back in via <code>/login</code>."
        )


@worker_router.message(Command("help"))
async def handle_worker_help(message: Message):
    """Display instructions for workers."""
    help_text = (
        "📖 <b>Specialist Help & Instructions</b>\n\n"
        "• <b>Authentication:</b>\n"
        "  - <code>/login</code> - Log in with admin credentials\n"
        "  - <code>/logout</code> - Sign out from receiving client inquiries\n\n"
        "• <b>Replying to Clients:</b>\n"
        "  - Use Telegram's <b>Reply</b> feature directly on the forwarded message.\n"
        "  - Click the <b>✍️ Reply to Client</b> button.\n"
        "  - Type <code>/reply &lt;client_id&gt; &lt;text&gt;</code>\n\n"
        "• <b>Status Tracking & Tools:</b>\n"
        "  - <code>/unanswered</code> - See all client inquiries marked as <i>not answered</i>.\n"
        "  - Replies automatically transition status to <b>answered</b> in PostgreSQL.\n\n"
        "• <b>Supported Message Types:</b>\n"
        "  - Text\n"
        "  - Voice messages (sent as voice notes to client)\n"
        "  - Photos & Documents"
    )
    await message.answer(help_text)


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
            client_id, _, db_msg_id = mapping

    # 2. Check if there is an active session for this chat if not replied
    if not client_id and message.chat.type == "private":
        client_id = await db.get_active_client_for_worker(message.chat.id)

    if not client_id:
        if message.chat.type == "private":
            await message.reply(
                "ℹ️ To answer a client, use Telegram's <b>Reply</b> on their message, "
                "or click <b>[ ✍️ Reply to Client ]</b>, or type <code>/reply &lt;id&gt; &lt;text&gt;</code>."
            )
        return

    answer_text = extract_message_summary(message)
    success = await send_content_to_client(message, client_id, client_bot)
    if success:
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
            await client_bot.send_message(
                chat_id=client_id,
                text=f"{prefix}[Unsupported media format sent by specialist]"
            )
            return True

    except Exception as e:
        logger.error(f"Failed to send content to client {client_id}: {e}")
        return False
