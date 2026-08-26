"""
SQLite orqali FAQ va 'o'rganilgan' javoblarni saqlash, va admin bilan
mijoz o'rtasidagi vaqtinchalik bog'lanishlarni kuzatish uchun modul.
"""

import sqlite3
from contextlib import contextmanager
from rapidfuzz import process, fuzz

DB_PATH = "bot.db"

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
