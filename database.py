import sqlite3
import os

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
            user_id        INTEGER PRIMARY KEY,
            username       TEXT,
            full_name      TEXT,
            balance        INTEGER DEFAULT 0,
            referral_code  TEXT UNIQUE,
            referred_by    INTEGER,
            referral_count INTEGER DEFAULT 0,
            referral_rewarded INTEGER DEFAULT 0,
            joined_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            plan_key     TEXT,
            plan_name    TEXT,
            plan_size    TEXT,
            price        INTEGER,
            status       TEXT DEFAULT 'pending',
            paid_with    TEXT DEFAULT 'card',
            created_at   TEXT DEFAULT (datetime('now')),
            confirmed_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER,
            amount          INTEGER,
            purpose         TEXT,
            ref_id          INTEGER,
            status          TEXT DEFAULT 'pending',
            receipt_file_id TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            confirmed_at    TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id  INTEGER PRIMARY KEY,
            added_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # کانفیگ‌ها با نوع پلن جداگانه
    c.execute("""
        CREATE TABLE IF NOT EXISTS configs (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_key TEXT NOT NULL,
            config   TEXT NOT NULL,
            is_used  INTEGER DEFAULT 0,
            used_by  INTEGER,
            used_at  TEXT
        )
    """)

    conn.commit()
    conn.close()


# ─── Settings ────────────────────────────────────────────

def get_setting(key: str, default=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()


# ─── Users ───────────────────────────────────────────────

def get_or_create_user(user_id: int, username: str, full_name: str, referred_by: int = None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    is_new = False
    if row is None:
        import random, string
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        c.execute(
            "INSERT INTO users (user_id,username,full_name,referral_code,referred_by) VALUES (?,?,?,?,?)",
            (user_id, username, full_name, code, referred_by)
        )
        conn.commit()
        is_new = True
        if referred_by:
            c.execute("UPDATE users SET referral_count=referral_count+1 WHERE user_id=?", (referred_by,))
            conn.commit()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
    else:
        c.execute("UPDATE users SET username=?,full_name=? WHERE user_id=?", (username, full_name, user_id))
        conn.commit()
    result = dict(row)
    conn.close()
    result["_is_new"] = is_new
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
    c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (delta, user_id))
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


def get_all_users():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY joined_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_all_user_ids():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = [r["user_id"] for r in c.fetchall()]
    conn.close()
    return rows


# ─── Subscriptions ───────────────────────────────────────

def create_subscription(user_id, plan_key, plan_name, plan_size, price, paid_with="card"):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO subscriptions (user_id,plan_key,plan_name,plan_size,price,paid_with) VALUES (?,?,?,?,?,?)",
        (user_id, plan_key, plan_name, plan_size, price, paid_with)
    )
    sub_id = c.lastrowid
    conn.commit()
    conn.close()
    return sub_id


def get_subscription(sub_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE id=?", (sub_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def confirm_subscription(sub_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE subscriptions SET status='confirmed',confirmed_at=datetime('now') WHERE id=?", (sub_id,))
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

def create_payment(user_id, amount, purpose, ref_id=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO payments (user_id,amount,purpose,ref_id) VALUES (?,?,?,?)",
        (user_id, amount, purpose, ref_id)
    )
    pay_id = c.lastrowid
    conn.commit()
    conn.close()
    return pay_id


def update_payment_receipt(pay_id, file_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE payments SET receipt_file_id=?,status='receipt_received' WHERE id=?", (file_id, pay_id))
    conn.commit()
    conn.close()


def confirm_payment(pay_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE payments SET status='confirmed',confirmed_at=datetime('now') WHERE id=?", (pay_id,))
    conn.commit()
    conn.close()


def cancel_payment(pay_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE payments SET status='cancelled' WHERE id=?", (pay_id,))
    conn.commit()
    conn.close()


def get_payment(pay_id):
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
        FROM payments p JOIN users u ON p.user_id=u.user_id
        WHERE p.status='receipt_received'
        ORDER BY p.created_at DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ─── Admins ──────────────────────────────────────────────

def add_admin(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()


def remove_admin(user_id):
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


# ─── Configs ─────────────────────────────────────────────

def add_configs(plan_key: str, configs: list):
    conn = get_conn()
    c = conn.cursor()
    for cfg in configs:
        if cfg.strip():
            c.execute("INSERT INTO configs (plan_key,config) VALUES (?,?)", (plan_key, cfg.strip()))
    conn.commit()
    conn.close()


def get_config_count(plan_key: str = None):
    conn = get_conn()
    c = conn.cursor()
    if plan_key:
        c.execute("SELECT COUNT(*) as cnt FROM configs WHERE plan_key=? AND is_used=0", (plan_key,))
    else:
        c.execute("SELECT COUNT(*) as cnt FROM configs WHERE is_used=0")
    row = c.fetchone()
    conn.close()
    return row["cnt"] if row else 0


def assign_config(plan_key: str, user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM configs WHERE plan_key=? AND is_used=0 ORDER BY id ASC LIMIT 1", (plan_key,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    c.execute(
        "UPDATE configs SET is_used=1,used_by=?,used_at=datetime('now') WHERE id=?",
        (user_id, row["id"])
    )
    conn.commit()
    conn.close()
    return row["config"]


def get_configs_summary():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT plan_key,
               SUM(CASE WHEN is_used=0 THEN 1 ELSE 0 END) as available,
               COUNT(*) as total
        FROM configs GROUP BY plan_key
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows
