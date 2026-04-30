import os
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG (RAILWAY)
# =========================
TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

API_URL = "https://router.huggingface.co/v1/chat/completions"

# =========================
# DATA MENU
# =========================
MENU = [
    {"name": "Nasi Ayam", "price": 7},
    {"name": "Nasi Ayam Special", "price": 9},
    {"name": "Ayam Crispy", "price": 8},
    {"name": "Mee Goreng", "price": 6},
    {"name": "Teh Ais", "price": 2.5},
]

cart = {}

# =========================
# AI FUNCTION
# =========================
def ask_ai(text):
    if not HF_TOKEN:
        return "AI belum setup."

    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "messages": [
            {"role": "system", "content": "Anda AI kedai makan. Jawab BM dan bantu jual makanan."},
            {"role": "user", "content": text}
        ]
    }

    try:
        res = requests.post(API_URL, headers=headers, json=payload)
        data = res.json()
        return data["choices"][0]["message"]["content"]
    except:
        return "AI error"

# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 Selamat datang 🔥\n\n"
        "👉 Taip 'menu' untuk tengok makanan\n"
        "👉 Contoh order: 'nasi ayam 2'\n"
    )

# =========================
# SHOW MENU
# =========================
async def show_menu(update):
    text = "🍽 MENU HARI INI\n\n"
    for i, item in enumerate(MENU, 1):
        text += f"{i}. {item['name']} RM{item['price']}\n"

    text += "\n👉 Taip nombor atau nama menu untuk order"

    await update.message.reply_text(text)

# =========================
# ADD TO CART
# =========================
def add_to_cart(user_id, item_name, qty=1):
    if user_id not in cart:
        cart[user_id] = []

    cart[user_id].append({"name": item_name, "qty": qty})

# =========================
# CHECKOUT
# =========================
async def checkout(update, user_id):
    items = cart.get(user_id, [])

    if not items:
        await update.message.reply_text("Cart kosong.")
        return

    text = "🧾 Order:\n\n"
    total = 0

    for item in items:
        price = next(x["price"] for x in MENU if x["name"] == item["name"])
        total += price * item["qty"]
        text += f"- {item['name']} x{item['qty']}\n"

    text += f"\nTotal: RM{total}"

    keyboard = [
        [InlineKeyboardButton("Confirm", callback_data="confirm")]
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =========================
# BUTTON
# =========================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    user_id = q.message.chat.id

    items = cart.get(user_id, [])
    total = 0
    text = ""

    for item in items:
        price = next(x["price"] for x in MENU if x["name"] == item["name"])
        total += price * item["qty"]
        text += f"{item['name']} x{item['qty']}\n"

    await context.bot.send_message(
        chat_id=OWNER_ID,
        text=f"ORDER BARU\n{text}\nTotal RM{total}"
    )

    await q.message.reply_text("Order dihantar ✅")
    cart[user_id] = []

# =========================
# CHAT HANDLER (SMART)
# =========================
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.lower()

    # buka menu
    if "menu" in text:
        await show_menu(update)
        return

    # checkout
    if "checkout" in text:
        await checkout(update, user_id)
        return

    # detect nombor
    if text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(MENU):
            item = MENU[index]
            add_to_cart(user_id, item["name"])
            await update.message.reply_text(f"✅ {item['name']} masuk cart")
            return

    # detect AI order (simple)
    for item in MENU:
        if item["name"].lower() in text:
            add_to_cart(user_id, item["name"])
            await update.message.reply_text(f"✅ {item['name']} masuk cart")
            return

    # fallback AI
    reply = ask_ai(text)
    await update.message.reply_text(reply)

# =========================
# MAIN
# =========================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

app.run_polling()
