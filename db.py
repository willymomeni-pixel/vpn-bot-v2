import sqlite3

db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    ref_count INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    plan TEXT,
    price INTEGER,
    status TEXT
)
""")

db.commit()


def get_user(uid):
    cur.execute("SELECT * FROM users WHERE id=?", (uid,))
    user = cur.fetchone()
    if not user:
        cur.execute("INSERT INTO users (id) VALUES (?)", (uid,))
        db.commit()
        return (uid, 0, 0)
    return user


def add_order(uid, plan, price):
    cur.execute(
        "INSERT INTO orders (user_id, plan, price, status) VALUES (?,?,?,?)",
        (uid, plan, price, "pending")
    )
    db.commit()


def get_last_order(uid):
    cur.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,))
    return cur.fetchone()


def pay_order(uid):
    cur.execute("UPDATE orders SET status='paid' WHERE user_id=? AND status='pending'", (uid,))
    db.commit()


def add_balance(uid, amount):
    cur.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, uid))
    db.commit()


def minus_balance(uid, amount):
    cur.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amount, uid))
    db.commit()
