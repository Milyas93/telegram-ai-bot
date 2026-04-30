import os
import re
import json
import requests
import mysql.connector
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

API_URL = "https://router.huggingface.co/v1/chat/completions"
AI_MODEL = "Qwen/Qwen2.5-7B-Instruct"

MENU = [
    {"id": "nasi_ayam", "name": "Nasi Ayam", "price": 7.00, "aliases": ["nasi ayam", "ayam"]},
    {"id": "nasi_ayam_special", "name": "Nasi Ayam Special", "price": 9.00, "aliases": ["nasi ayam special", "special"]},
    {"id": "ayam_crispy", "name": "Ayam Crispy", "price": 8.00, "aliases": ["ayam crispy", "crispy"]},
    {"id": "mee_goreng", "name": "Mee Goreng", "price": 6.00, "aliases": ["mee goreng", "mee"]},
    {"id": "teh_ais", "name": "Teh Ais", "price": 2.50, "aliases": ["teh ais", "teh"]},
    {"id": "milo_ais", "name": "Milo Ais", "price": 3.50, "aliases": ["milo ais", "milo"]},
    {"id": "air_mineral", "name": "Air Mineral", "price": 1.50, "aliases": ["air mineral", "mineral", "air"]},
]

cart = {}
chat_history = {}


def get_db():
    return mysql.connector.connect(
        host=os.getenv("MYSQLHOST"),
        user=os.getenv("MYSQLUSER"),
        password=os.getenv("MYSQLPASSWORD"),
        database=os.getenv("MYSQLDATABASE"),
        port=int(os.getenv("MYSQLPORT", "3306")),
    )


def init_db():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                customer_id BIGINT,
                customer_name VARCHAR(255),
                items JSON,
                total DECIMAL(10,2),
                status VARCHAR(50) DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()
        cursor.close()
        db.close()
        print("Database ready.")
    except Exception as e:
        print("Database init error:", e)


def save_order(customer_id, customer_name, items, total):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO orders (customer_id, customer_name, items, total, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                customer_id,
                customer_name,
                json.dumps(items),
                total,
                "new",
            ),
        )
        db.commit()
        order_id = cursor.lastrowid
        cursor.close()
        db.close()
        return order_id
    except Exception as e:
        print("Save order error:", e)
        return None


def menu_text():
    return "\n".join(f"- {item['name']} RM{item['price']:.2f}" for item in MENU)


def ask_ai(user_id, user_text):
    if not HF_TOKEN:
        return "AI belum setup. Tapi boleh taip 'menu' untuk order."

    chat_history.setdefault(user_id, [])

    system_prompt = f"""
Awak ialah AI staff kedai makan.

Menu:
{menu_text()}

Tugas:
- Jawab dalam Bahasa Melayu santai.
- Jangan reka menu/harga.
- Kalau customer nak order, ajar dia taip contoh: nasi ayam 2 teh ais 1.
- Kalau customer tanya cadangan, cadangkan menu yang ada sahaja.
"""

    messages = [{"role": "system", "content": system_prompt}]
    messages += chat_history[user_id][-6:]
    messages.append({"role": "user", "content": user_text})

    try:
        res = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {HF_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "messages": messages,
                "max_tokens": 250,
                "temperature": 0.7,
            },
            timeout=30,
        )

        data = res.json()

        if res.status_code != 200:
            print("AI ERROR:", data)
            return "AI tengah busy. Taip 'menu' untuk order dulu."

        reply = data["choices"][0]["message"]["content"].strip()
        chat_history[user_id].append({"role": "user", "content": user_text})
        chat_history[user_id].append({"role": "assistant", "content": reply})
        return reply

    except Exception as e:
        print("AI EXCEPTION:", e)
        return "AI error sekejap. Taip 'menu' untuk order dulu."


def get_user_cart(user_id):
    if user_id not in cart:
        cart[user_id] = {}
    return cart[user_id]


def add_item(user_id, item, qty):
    user_cart = get_user_cart(user_id)

    if item["id"] not in user_cart:
        user_cart[item["id"]] = {
            "name": item["name"],
            "price": item["price"],
            "qty": 0,
        }

    user_cart[item["id"]]["qty"] += qty


def cart_summary(user_id):
    user_cart = get_user_cart(user_id)

    if not user_cart:
        return "Cart kosong.", 0

    text = "🧾 Cart anda:\n\n"
    total = 0

    for item in user_cart.values():
        subtotal = item["price"] * item["qty"]
        total += subtotal
        text += f"- {item['name']} x{item['qty']} = RM{subtotal:.2f}\n"

    text += f"\nTotal: RM{total:.2f}"
    return text, total


def parse_order_text(text):
    text = text.lower()
    found = []

    sorted_menu = sorted(
        MENU,
        key=lambda x: max(len(a) for a in x["aliases"]),
        reverse=True,
    )

    used_spans = []

    for item in sorted_menu:
        for alias in sorted(item["aliases"], key=len, reverse=True):
            for match in re.finditer(re.escape(alias), text):
                start, end = match.span()

                overlap = any(not (end <= s or start >= e) for s, e in used_spans)
                if overlap:
                    continue

                before = text[max(0, start - 6):start]
                after = text[end:end + 8]

                qty = 1

                before_num = re.search(r"(\d+)\s*$", before)
                if before_num:
                    qty = int(before_num.group(1))

                after_num = re.search(r"^\s*(\d+)", after)
                if after_num:
                    qty = int(after_num.group(1))

                found.append((item, qty))
                used_spans.append((start, end))
                break

    return found


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 Selamat datang ke Kedai AI 🔥\n\n"
        "Taip:\n"
        "• menu\n"
        "• nasi ayam 2 teh ais 1\n"
        "• cart\n"
        "• checkout\n"
        "• cancel\n"
        "• /id"
    )


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🍽 MENU HARI INI\n\n"

    for i, item in enumerate(MENU, 1):
        text += f"{i}. {item['name']} — RM{item['price']:.2f}\n"

    text += "\nContoh order: nasi ayam 2 teh ais 1"
    await update.message.reply_text(text)


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Telegram ID anda: {update.effective_chat.id}")


async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, _ = cart_summary(update.effective_user.id)
    await update.message.reply_text(text)


async def do_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, total = cart_summary(user_id)

    if total == 0:
        await update.message.reply_text("Cart kosong. Taip menu untuk pilih makanan.")
        return

    await update.message.reply_text(
        text + "\n\nConfirm order?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Confirm ✅", callback_data="confirm_order")],
            [InlineKeyboardButton("Cancel ❌", callback_data="cancel_order")],
        ]),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_cart = get_user_cart(user_id)

    if query.data == "cancel_order":
        cart[user_id] = {}
        await query.message.reply_text("Order dibatalkan ❌")
        return

    if query.data == "confirm_order":
        if not user_cart:
            await query.message.reply_text("Cart kosong.")
            return

        if OWNER_ID == 0:
            await query.message.reply_text("OWNER_ID belum set di Railway Variables.")
            return

        text, total = cart_summary(user_id)

        customer_name = query.from_user.first_name or "Customer"
        customer_id = query.from_user.id

        items_for_db = list(user_cart.values())
        order_id = save_order(
            customer_id=customer_id,
            customer_name=customer_name,
            items=items_for_db,
            total=total,
        )

        order_label = f"#{order_id}" if order_id else "(DB gagal simpan)"

        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=(
                f"ORDER BARU {order_label} 🔔\n\n"
                f"Customer: {customer_name}\n"
                f"Telegram ID: {customer_id}\n\n"
                f"{text}"
            ),
        )

        cart[user_id] = {}
        await query.message.reply_text(f"Order berjaya dihantar ✅\nOrder ID: {order_label}")
        return


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    low = text.lower()

    if low in ["menu", "/menu"]:
        await show_menu(update, context)
        return

    if low in ["cart", "troli"]:
        await show_cart(update, context)
        return

    if low in ["checkout", "check out", "bayar", "confirm"]:
        await do_checkout(update, context)
        return

    if low in ["cancel", "clear", "kosongkan"]:
        cart[user_id] = {}
        await update.message.reply_text("Cart dikosongkan ✅")
        return

    if re.fullmatch(r"[\d\s]+", low):
        nums = [int(x) for x in low.split() if x.isdigit()]
        added = []

        for n in nums:
            if 1 <= n <= len(MENU):
                item = MENU[n - 1]
                add_item(user_id, item, 1)
                added.append(f"✅ {item['name']} x1")

        if added:
            await update.message.reply_text("\n".join(added) + "\n\nTaip cart atau checkout.")
            return

    parsed_items = parse_order_text(low)

    if parsed_items:
        lines = []

        for item, qty in parsed_items:
            add_item(user_id, item, qty)
            lines.append(f"✅ {item['name']} x{qty} masuk cart")

        await update.message.reply_text("\n".join(lines) + "\n\nTaip cart atau checkout.")
        return

    reply = ask_ai(user_id, text)
    await update.message.reply_text(reply[:4000])


def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_TOKEN belum set di Railway Variables.")

    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("Bot database version running...")
    app.run_polling()


if __name__ == "__main__":
    main()
