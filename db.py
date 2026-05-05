import sqlite3

db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    ref_by INTEGER,
    ref_count INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    plan TEXT,
    price INTEGER,
    type TEXT,
    status TEXT,
    expire INTEGER
)
""")

db.commit()


def get_user(uid):
    cur.execute("SELECT * FROM users WHERE id=?", (uid,))
    u = cur.fetchone()
    if not u:
        cur.execute("INSERT INTO users (id) VALUES (?)", (uid,))
        db.commit()
        return (uid, 0, None, 0)
    return u


def set_ref(user, ref):
    if ref:
        cur.execute("UPDATE users SET ref_by=? WHERE id=?", (ref, user))
        cur.execute("UPDATE users SET ref_count = ref_count + 1 WHERE id=?", (ref,))
        db.commit()


def add_order(uid, plan, price, t):
    cur.execute(
        "INSERT INTO orders (user_id, plan, price, type, status, expire) VALUES (?,?,?,?,?,?)",
        (uid, plan, price, t, "pending", 0)
    )
    db.commit()


def last_order(uid):
    cur.execute("SELECT * FROM orders WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1", (uid,))
    return cur.fetchone()


def pay(uid):
    cur.execute("UPDATE orders SET status='paid' WHERE user_id=? AND status='pending'", (uid,))
    db.commit()


def set_expire(uid, exp):
    cur.execute("UPDATE orders SET expire=? WHERE user_id=? AND status='pending'", (exp, uid))
    db.commit()


def add_balance(uid, amount):
    cur.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, uid))
    db.commit()


def use_balance(uid, amount):
    cur.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amount, uid))
    db.commit()
