"""
Sotuv AI boti.

Mantiq:
1. Mijoz savol yozadi.
2. Agar bot shu mijoz uchun "pauza"da bo'lsa (admin qo'lda javob berayotgan
   payt) -> AI chaqirilmaydi, savol to'g'ridan-to'g'ri adminga yuboriladi
   ("Reply" orqali javob berish mumkin, eski mexanizm bilan bir xil).
3. Pauzada bo'lmasa -> avval oddiy salomlashuv tekshiriladi, keyin savol
   Gemini AI'ga yuboriladi (bilim bazasi bilan birga).
4. AI bilim bazasi doirasida javob bera olsa -> shu javob mijozga yuboriladi.
5. AI "ESCALATE" desa (savol bilim bazasidan tashqarida) -> mijozga
   "menejer bog'lanadi" xabari, adminga signal + "Botni to'xtatish/yoqish"
   tugmasi bilan yuboriladi, va shu mijoz uchun bot 1 soatga avtomatik
   pauzaga o'tadi (yoki admin tugma orqali qo'lda boshqaradi).
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

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
import ai

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

import re

# Oddiy muloqot (salomlashish, minnatdorchilik va h.k.) — bularga bot
# hech qanday admin signalisiz, to'g'ridan-to'g'ri o'zi javob beradi.
# MUHIM: endi so'z BUTUNLIGICHA mos kelishi tekshiriladi (substring emas),
# aks holda "qildirmoqchiman" kabi so'zlar ichidagi tasodifiy harf
# ketma-ketligi ("...moqCHIman" ichida "hi") xato ishga tushib qolardi.
SMALL_TALK = [
    (
        {"salom", "assalomu", "alaykum", "salomlar", "hi", "hello", "hey"},
        "Assalomu alaykum! Sizga qanday yordam bera olaman?",
    ),
    (
        {"rahmat", "raxmat", "tashakkur", "thanks", "rahmatlar"},
        "Arzimaydi! Boshqa savolingiz bo'lsa, yozavering.",
    ),
    (
        {"xayr", "bye", "hayr"},
        "Xayr! Yana savolingiz bo'lsa, shu yerdaman.",
    ),
    (
        {"yaxshimisiz", "qalaysiz", "yahshimisiz", "qalesiz"},
        "Rahmat, hammasi zo'r! Sizga qanday yordam bera olaman?",
    ),
]


def find_small_talk_reply(text: str) -> str | None:
    words = set(re.findall(r"[a-zA-Zʻʼ'\u0400-\u04FF]+", text.lower()))
    for keywords, reply in SMALL_TALK:
        if words & keywords:
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

    # Agar shu mijoz uchun bot pauzada bo'lsa (admin qo'lda javob berayapti) —
    # AI chaqirilmaydi, xabar to'g'ridan-to'g'ri adminga yo'naltiriladi.
    if db.is_paused(chat_id):
        await forward_to_admin(context, chat_id, update.effective_user.full_name, text)
        return

    small_talk_reply = find_small_talk_reply(text)
    if small_talk_reply:
        await update.message.reply_text(small_talk_reply)
        return

    # Tez-tez so'raladigan, admin qo'lda qo'shgan savollarni avval tekshiramiz
    # (bepul va tezroq) — topilmasa AI'ga murojaat qilamiz.
    faq_answer = db.find_answer(text)
    if faq_answer:
        await update.message.reply_text(faq_answer)
        return

    try:
        ai_answer = ai.ask_ai(text)
    except Exception:
        logger.exception("Gemini so'roviga xatolik yuz berdi")
        ai_answer = None

    if ai_answer:
        await update.message.reply_text(ai_answer)
        return

    # AI bilim bazasidan tashqari deb topdi -> adminga yo'naltiramiz va pauzaga qo'yamiz
    db.pause_chat(chat_id)
    await forward_to_admin(
        context, chat_id, update.effective_user.full_name, text, is_escalation=True
    )
    await update.message.reply_text(
        "Savolingizni menejerimizga yo'naltirdim, tez orada bog'lanadi."
    )


async def forward_to_admin(
    context: ContextTypes.DEFAULT_TYPE,
    customer_chat_id: int,
    customer_name: str,
    question: str,
    is_escalation: bool = False,
):
    """Mijoz savolini adminga yuboradi, javob berish uchun Reply qilinishi kerak."""
    header = "🔔 AI bilmagan savol!" if is_escalation else "✉️ Mijoz xabari (bot pauzada)"
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔁 Bot holatini almashtirish", callback_data=f"toggle:{customer_chat_id}")]]
    )
    admin_msg = await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=(
            f"{header}\n\n"
            f"Mijoz: {customer_name} (id: {customer_chat_id})\n"
            f"Savol: {question}\n\n"
            "Javob berish uchun shu xabarga Reply qiling."
        ),
        reply_markup=keyboard,
    )
    db.save_pending_question(admin_msg.message_id, customer_chat_id, question)


async def handle_toggle_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    customer_chat_id = int(query.data.split(":")[1])
    now_paused = db.toggle_manual_pause(customer_chat_id)

    status = "⏸ Bot ushbu mijoz uchun TO'XTATILDI" if now_paused else "▶️ Bot ushbu mijoz uchun YOQILDI"
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=status)


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

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("del", cmd_del))
    app.add_handler(CallbackQueryHandler(handle_save_choice, pattern=r"^save_"))
    app.add_handler(CallbackQueryHandler(handle_toggle_pause, pattern=r"^toggle:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot ishga tushdi (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
