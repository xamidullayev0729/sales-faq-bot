"""
SQLite orqali FAQ va 'o'rganilgan' javoblarni saqlash, va admin bilan
mijoz o'rtasidagi vaqtinchalik bog'lanishlarni kuzatish uchun modul.
"""

import os
import sqlite3
import time
from contextlib import contextmanager
from rapidfuzz import process, fuzz

# Railway'da doimiy Volume ulanganda, uni masalan /data ga mount qilib,
# DB_PATH environment variable orqali /data/bot.db qilib ko'rsatish kerak.
# Aks holda konteyner qayta ishga tushganda baza o'chib ketadi.
DB_PATH = os.environ.get("DB_PATH", "bot.db")

# FAQ'ga mos deb hisoblanadigan minimal o'xshashlik foizi (0-100)
MATCH_THRESHOLD = 80


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS faq (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS learned_faq (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL
            )"""
        )
        # Admin xabariga bog'langan, hali javob berilmagan mijoz savoli
        conn.execute(
            """CREATE TABLE IF NOT EXISTS pending_questions (
                admin_message_id INTEGER PRIMARY KEY,
                customer_chat_id INTEGER NOT NULL,
                question TEXT NOT NULL
            )"""
        )
        # Admin javob bergandan keyin, "saqlaymizmi?" tasdiqlanishini kutayotgan yozuv
        conn.execute(
            """CREATE TABLE IF NOT EXISTS pending_saves (
                confirm_message_id INTEGER PRIMARY KEY,
                question TEXT NOT NULL,
                answer TEXT NOT NULL
            )"""
        )
        # Har bir mijoz uchun bot "pauza"da yoki yo'qligini kuzatish:
        # paused_until — vaqtinchalik (1 soatlik) pauza tugash vaqti (unix timestamp)
        # manual_override — 1 bo'lsa, admin qo'lda o'chirgan, vaqt tugashiga qaramay pauza davom etadi
        conn.execute(
            """CREATE TABLE IF NOT EXISTS pause_state (
                chat_id INTEGER PRIMARY KEY,
                paused_until INTEGER NOT NULL DEFAULT 0,
                manual_override INTEGER NOT NULL DEFAULT 0
            )"""
        )


def seed_if_empty(seed_pairs: list[tuple[str, str]]):
    """Agar faq jadvali bo'sh bo'lsa, boshlang'ich namuna savol-javoblarni qo'shadi."""
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM faq").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO faq (question, answer) VALUES (?, ?)", seed_pairs
            )


def find_answer(user_question: str) -> str | None:
    """Avval doimiy FAQ'dan, keyin o'rganilgan javoblardan eng mos javobni qidiradi."""
    with get_conn() as conn:
        rows = conn.execute("SELECT question, answer FROM faq").fetchall()
        rows += conn.execute("SELECT question, answer FROM learned_faq").fetchall()

    if not rows:
        return None

    questions = [r["question"] for r in rows]
    match = process.extractOne(user_question, questions, scorer=fuzz.WRatio)
    if match is None:
        return None

    matched_text, score, idx = match
    if score >= MATCH_THRESHOLD:
        return rows[idx]["answer"]
    return None


def save_pending_question(admin_message_id: int, customer_chat_id: int, question: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO pending_questions (admin_message_id, customer_chat_id, question) "
            "VALUES (?, ?, ?)",
            (admin_message_id, customer_chat_id, question),
        )


def pop_pending_question(admin_message_id: int):
    """Berilgan admin xabari ID'siga mos yozuvni o'qiydi va o'chiradi."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT customer_chat_id, question FROM pending_questions WHERE admin_message_id = ?",
            (admin_message_id,),
        ).fetchone()
        if row:
            conn.execute(
                "DELETE FROM pending_questions WHERE admin_message_id = ?",
                (admin_message_id,),
            )
    return row


def save_pending_save(confirm_message_id: int, question: str, answer: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO pending_saves (confirm_message_id, question, answer) VALUES (?, ?, ?)",
            (confirm_message_id, question, answer),
        )


def pop_pending_save(confirm_message_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT question, answer FROM pending_saves WHERE confirm_message_id = ?",
            (confirm_message_id,),
        ).fetchone()
        if row:
            conn.execute(
                "DELETE FROM pending_saves WHERE confirm_message_id = ?",
                (confirm_message_id,),
            )
    return row


def add_learned_faq(question: str, answer: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO learned_faq (question, answer) VALUES (?, ?)",
            (question, answer),
        )


PAUSE_DURATION_SECONDS = 60 * 60  # 1 soat


def pause_chat(chat_id: int):
    """Shu mijoz uchun botni 1 soatga avtomatik pauzaga qo'yadi."""
    until = int(time.time()) + PAUSE_DURATION_SECONDS
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO pause_state (chat_id, paused_until, manual_override)
               VALUES (?, ?, 0)
               ON CONFLICT(chat_id) DO UPDATE SET paused_until = excluded.paused_until"""
            ,
            (chat_id, until),
        )


def is_paused(chat_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT paused_until, manual_override FROM pause_state WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    if not row:
        return False
    if row["manual_override"]:
        return True
    return row["paused_until"] > int(time.time())


def toggle_manual_pause(chat_id: int) -> bool:
    """
    Admin tugmasi bosilganda chaqiriladi.

    Hozirgi HAQIQIY holatga (avtomatik yoki qo'lda pauza bo'lishidan qat'iy
    nazar) qarab teskarisiga o'tkazadi:
    - Hozir pauzada bo'lsa (avtomatik yoki qo'lda) -> to'liq yoqiladi
      (ham manual_override, ham vaqtinchalik pauza tozalanadi).
    - Hozir pauzada bo'lmasa -> qo'lda pauzaga qo'yiladi.

    Yangi holatni qaytaradi (True = endi pauzada).
    """
    currently_paused = is_paused(chat_id)
    new_manual = 0 if currently_paused else 1
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO pause_state (chat_id, paused_until, manual_override)
               VALUES (?, 0, ?)
               ON CONFLICT(chat_id) DO UPDATE
               SET paused_until = 0, manual_override = excluded.manual_override""",
            (chat_id, new_manual),
        )
    return bool(new_manual)


def add_faq(question: str, answer: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO faq (question, answer) VALUES (?, ?)", (question, answer)
        )
        return cur.lastrowid


def list_all_faq():
    """faq va learned_faq jadvallaridagi barcha yozuvlarni birga qaytaradi.

    Har bir qator (manba, id, savol, javob) shaklida bo'ladi, manba 'faq'
    yoki 'learned' bo'ladi — o'chirishda qaysi jadvaldan olib tashlashni
    bilish uchun kerak.
    """
    with get_conn() as conn:
        faq_rows = conn.execute("SELECT id, question, answer FROM faq").fetchall()
        learned_rows = conn.execute(
            "SELECT id, question, answer FROM learned_faq"
        ).fetchall()
    result = [("faq", r["id"], r["question"], r["answer"]) for r in faq_rows]
    result += [("learned", r["id"], r["question"], r["answer"]) for r in learned_rows]
    return result


def delete_faq(source: str, entry_id: int):
    table = "faq" if source == "faq" else "learned_faq"
    with get_conn() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (entry_id,))
