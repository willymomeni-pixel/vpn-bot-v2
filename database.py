import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "bot.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            full_name   TEXT,
            balance     INTEGER DEFAULT 0,
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            referral_count INTEGER DEFAULT 0,
            referral_rewarded INTEGER DEFAULT 0,
            joined_at   TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            plan_key    TEXT,
            plan_name   TEXT,
            plan_size   TEXT,
            price       INTEGER,
            status      TEXT DEFAULT 'pending',
            paid_with   TEXT DEFAULT 'card',
            created_at  TEXT DEFAULT (datetime('now')),
            confirmed_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            amount      INTEGER,
            purpose     TEXT,
            ref_id      INTEGER,
            status      TEXT DEFAULT 'pending',
            receipt_file_id TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            confirmed_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id     INTEGER PRIMARY KEY,
            added_at    TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()


# ─── Users ───────────────────────────────────────────────

def get_or_create_user(user_id: int, username: str, full_name: str, referred_by: int = None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row is None:
        import random, string
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        c.execute(
            "INSERT INTO users (user_id, username, full_name, referral_code, referred_by) VALUES (?,?,?,?,?)",
            (user_id, username, full_name, code, referred_by)
        )
        conn.commit()
        # افزایش شمارنده دعوت‌کننده
        if referred_by:
            c.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id=?", (referred_by,))
            conn.commit()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
    else:
        # آپدیت اطلاعات
        c.execute("UPDATE users SET username=?, full_name=? WHERE user_id=?", (username, full_name, user_id))
        conn.commit()
    result = dict(row)
    conn.close()
    return result


def get_user(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_balance(user_id: int, delta: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (delta, user_id))
    conn.commit()
    conn.close()


def set_balance(user_id: int, amount: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET balance=? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()


def get_user_by_referral(code: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE referral_code=?", (code,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def mark_referral_rewarded(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET referral_rewarded=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def get_referral_count(user_id: int) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT referral_count FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row["referral_count"] if row else 0


# ─── Subscriptions ───────────────────────────────────────

def create_subscription(user_id: int, plan_key: str, plan_name: str, plan_size: str, price: int, paid_with: str = "card"):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO subscriptions (user_id, plan_key, plan_name, plan_size, price, paid_with) VALUES (?,?,?,?,?,?)",
        (user_id, plan_key, plan_name, plan_size, price, paid_with)
    )
    sub_id = c.lastrowid
    conn.commit()
    conn.close()
    return sub_id


def confirm_subscription(sub_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE subscriptions SET status='confirmed', confirmed_at=datetime('now') WHERE id=?",
        (sub_id,)
    )
    conn.commit()
    conn.close()


def get_user_subscriptions(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE user_id=? ORDER BY created_at DESC", (user_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ─── Payments ────────────────────────────────────────────

def create_payment(user_id: int, amount: int, purpose: str, ref_id: int = None) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO payments (user_id, amount, purpose, ref_id) VALUES (?,?,?,?)",
        (user_id, amount, purpose, ref_id)
    )
    pay_id = c.lastrowid
    conn.commit()
    conn.close()
    return pay_id


def update_payment_receipt(pay_id: int, file_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE payments SET receipt_file_id=?, status='receipt_received' WHERE id=?", (file_id, pay_id))
    conn.commit()
    conn.close()


def confirm_payment(pay_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE payments SET status='confirmed', confirmed_at=datetime('now') WHERE id=?",
        (pay_id,)
    )
    conn.commit()
    conn.close()


def cancel_payment(pay_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE payments SET status='cancelled' WHERE id=?", (pay_id,))
    conn.commit()
    conn.close()


def get_payment(pay_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE id=?", (pay_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_pending_payments():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT p.*, u.username, u.full_name 
        FROM payments p JOIN users u ON p.user_id = u.user_id
        WHERE p.status='receipt_received'
        ORDER BY p.created_at DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ─── Admins ──────────────────────────────────────────────

def add_admin(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()


def remove_admin(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def get_admin_ids():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins")
    rows = [r["user_id"] for r in c.fetchall()]
    conn.close()
    return rows


def get_all_users():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY joined_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows
