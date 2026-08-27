"""
Sotuv FAQ boti.

Mantiq:
1. Mijoz savol yozadi.
2. Bot FAQ + o'rganilgan javoblar orasidan mos javobni qidiradi (rapidfuzz).
3. Topilsa -> mijozga avtomatik javob beriladi.
4. Topilmasa -> admin (siz)ga xabar boradi. Siz o'sha xabarga "Reply" qilib
   javob yozasiz -> bot javobingizni mijozga yetkazadi -> sizdan
   "FAQ'ga saqlaymizmi?" deb so'raydi (Ha/Yo'q tugmalari bilan).
5. "Ha" bosilsa, savol-javob juftligi saqlanadi va keyingi safar shunga
   o'xshash savolga bot o'zi avtomatik javob beradi.
"""

import logging
import os

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database as db

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Boshlang'ich namuna savol-javoblar — FAQ ro'yxatingiz tayyor bo'lguncha
# shu bir nechta misol bilan botni sinab ko'rishingiz mumkin.
SEED_FAQ = [
    ("ish vaqtingiz qachon", "Biz har kuni 9:00 dan 18:00 gacha ishlaymiz."),
    ("yetkazib berish qancha turadi", "Toshkent bo'ylab yetkazib berish bepul."),
    ("qanday to'lov qilsam bo'ladi", "Naqd pul yoki karta orqali to'lov qilishingiz mumkin."),
]


# Oddiy muloqot (salomlashish, minnatdorchilik va h.k.) — bularga bot
# hech qanday admin signalisiz, to'g'ridan-to'g'ri o'zi javob beradi.
# Har bir kalit so'z mijoz xabarida uchrasa, mos javob qaytariladi.
SMALL_TALK = [
    (
        ["salom", "assalomu alaykum", "salomlar", "hi", "hello", "hey"],
        "Assalomu alaykum! Sizga qanday yordam bera olaman?",
    ),
    (
        ["rahmat", "raxmat", "tashakkur", "thanks", "rahmatlar"],
        "Arzimaydi! Boshqa savolingiz bo'lsa, yozavering.",
    ),
    (
        ["xayr", "ko'rishguncha", "bye", "hayr"],
        "Xayr! Yana savolingiz bo'lsa, shu yerdaman.",
    ),
    (
        ["yaxshimisiz", "qalaysiz", "yahshimisiz", "qalesiz", "how are you"],
        "Rahmat, hammasi zo'r! Sizga qanday yordam bera olaman?",
    ),
]


def find_small_talk_reply(text: str) -> str | None:
    lowered = text.lower()
    for keywords, reply in SMALL_TALK:
        if any(keyword in lowered for keyword in keywords):
            return reply
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Assalomu alaykum! Savolingizni yozing, imkon qadar tezroq javob beramiz."
    )


def _admin_only(update: Update) -> bool:
    return update.effective_chat.id == ADMIN_CHAT_ID


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanish: /add Savol matni | Javob matni"""
    if not _admin_only(update):
        return

    raw = update.message.text.partition(" ")[2]  # "/add " dan keyingi qism
    if "|" not in raw:
        await update.message.reply_text(
            "Noto'g'ri format. Shunday yozing:\n/add Savol matni | Javob matni"
        )
        return

    question, _, answer = raw.partition("|")
    question, answer = question.strip(), answer.strip()
    if not question or not answer:
        await update.message.reply_text(
            "Savol yoki javob bo'sh bo'lmasligi kerak.\n/add Savol matni | Javob matni"
        )
        return

    entry_id = db.add_faq(question, answer)
    await update.message.reply_text(f"✅ Qo'shildi (№{entry_id}):\nSavol: {question}\nJavob: {answer}")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha FAQ yozuvlarini ko'rsatadi."""
    if not _admin_only(update):
        return

    rows = db.list_all_faq()
    if not rows:
        await update.message.reply_text("Hozircha FAQ bazasi bo'sh.")
        return

    lines = ["📋 FAQ ro'yxati (o'chirish uchun: /del <turi> <raqam>):\n"]
    for source, entry_id, question, answer in rows:
        lines.append(f"[{source} #{entry_id}] {question} → {answer}")
    # Telegram bitta xabarga ~4096 belgi sig'diradi, shuning uchun bo'lib yuboramiz
    message = "\n".join(lines)
    for chunk_start in range(0, len(message), 3500):
        await update.message.reply_text(message[chunk_start:chunk_start + 3500])


async def cmd_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanish: /del faq 3  yoki  /del learned 5 (raqamni /list dan oling)"""
    if not _admin_only(update):
        return

    parts = update.message.text.split()
    if len(parts) != 3 or parts[1] not in ("faq", "learned") or not parts[2].isdigit():
        await update.message.reply_text("Foydalanish: /del faq 3  yoki  /del learned 5")
        return

    db.delete_faq(parts[1], int(parts[2]))
    await update.message.reply_text("🗑 O'chirildi.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text or ""

    # --- Holat 1: admin mijoz savoliga "Reply" qilib javob yozmoqda ---
    if chat_id == ADMIN_CHAT_ID and update.message.reply_to_message:
        replied_id = update.message.reply_to_message.message_id
        pending = db.pop_pending_question(replied_id)
        if pending:
            customer_chat_id = pending["customer_chat_id"]
            question = pending["question"]
            answer = text

            # Javobni mijozga yetkazish
            await context.bot.send_message(chat_id=customer_chat_id, text=answer)

            # Admindan saqlashni so'rash
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Ha, saqlash", callback_data="save_yes"),
                        InlineKeyboardButton("Yo'q", callback_data="save_no"),
                    ]
                ]
            )
            confirm_msg = await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    "Javob mijozga yuborildi.\n\n"
                    f"Savol: {question}\n"
                    f"Javob: {answer}\n\n"
                    "Bu javobni FAQ bazasiga saqlaymizmi?"
                ),
                reply_markup=keyboard,
            )
            db.save_pending_save(confirm_msg.message_id, question, answer)
            return
        # Admin boshqa, aloqasi yo'q xabarga reply qilgan bo'lsa — e'tiborsiz qoldiramiz
        return

    # --- Holat 2: oddiy mijoz xabari ---
    if chat_id == ADMIN_CHAT_ID:
        return  # admin o'zi botga oddiy yozsa, hech narsa qilmaymiz

    small_talk_reply = find_small_talk_reply(text)
    if small_talk_reply:
        await update.message.reply_text(small_talk_reply)
        return

    answer = db.find_answer(text)
    if answer:
        await update.message.reply_text(answer)
        return

    # Javob topilmadi — adminga yuboramiz
    admin_msg = await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=(
            "🔔 Javobsiz savol!\n\n"
            f"Mijoz: {update.effective_user.full_name} (id: {chat_id})\n"
            f"Savol: {text}\n\n"
            "Javob berish uchun shu xabarga Reply qiling."
        ),
    )
    db.save_pending_question(admin_msg.message_id, chat_id, text)

    await update.message.reply_text(
        "Savolingiz operatorga yuborildi, tez orada javob beramiz."
    )


async def handle_save_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pending = db.pop_pending_save(query.message.message_id)
    if not pending:
        await query.edit_message_text("Bu so'rov muddati o'tgan.")
        return

    if query.data == "save_yes":
        db.add_learned_faq(pending["question"], pending["answer"])
        await query.edit_message_text("Saqlandi. Keyingi safar shunga o'xshash savolga bot o'zi javob beradi.")
    else:
        await query.edit_message_text("Saqlanmadi.")


def main():
    db.init_db()
    db.seed_if_empty(SEED_FAQ)

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("del", cmd_del))
    app.add_handler(CallbackQueryHandler(handle_save_choice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot ishga tushdi (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
