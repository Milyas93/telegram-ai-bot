import os
import urllib.parse
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
# 🔥 CONFIG (JANGAN LETAK TOKEN DALAM CODE)
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")   # 👉 isi di Railway
HF_TOKEN = os.getenv("HF_TOKEN")               # 👉 isi di Railway
OWNER_ID = int(os.getenv("OWNER_ID", "0"))     # 👉 isi di Railway

API_URL = "https://router.huggingface.co/v1/chat/completions"

# =========================
# MENU KEDAI
# =========================
SHOP = {
    "name": "Kedai Nasi Ayam Pak Ali",
    "menu": [
        {"no": 1, "name": "Nasi Ayam", "price": 7.00, "image": "https://picsum.photos/400"},
        {"no": 2, "name": "Nasi Lemak", "price": 6.00, "image": "https://picsum.photos/401"},
        {"no": 3, "name": "Mee Goreng", "price": 5.00, "image": "https://picsum.photos/402"},
    ]
}

chat_history = {}
user_cart = {}

# =========================
# AI FUNCTION
# =========================
def ask_ai(user_id, text):
    if not HF_TOKEN:
        return "AI belum setup. Taip menu dulu."

    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "messages": [
            {"role": "system", "content": "Anda AI kedai makan. Jawab ringkas BM."},
            {"role": "user", "content": text}
        ]
    }

    try:
        res = requests.post(API_URL, headers=headers, json=payload)
        data = res.json()
        return data["choices"][0]["message"]["content"]
    except:
        return "AI error. Taip menu."

# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! 🤖\n"
        "Taip 'menu' untuk order\n"
        "/id untuk tengok ID"
    )

# =========================
# GET ID
# =========================
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"ID: {update.effective_chat.id}")

# =========================
# MENU
# =========================
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_cart[chat_id] = []

    for item in SHOP["menu"]:
        keyboard = [[InlineKeyboardButton(
            f"No {item['no']}",
            callback_data=f"add_{item['no']}"
        )]]

        await context.bot.send_photo(
            chat_id=chat_id,
            photo=item["image"],
            caption=f"{item['name']} RM{item['price']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    await context.bot.send_message(
        chat_id=chat_id,
        text="Checkout",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Checkout", callback_data="checkout")]]
        )
    )

# =========================
# BUTTON
# =========================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    chat_id = q.message.chat.id
    data = q.data

    if chat_id not in user_cart:
        user_cart[chat_id] = []

    if data.startswith("add_"):
        no = int(data.replace("add_", ""))
        item = next(x for x in SHOP["menu"] if x["no"] == no)
        user_cart[chat_id].append(item)

        await q.message.reply_text(f"Tambah {item['name']}")

    elif data == "checkout":
        cart = user_cart[chat_id]

        total = sum(x["price"] for x in cart)
        text = "\n".join([x["name"] for x in cart])

        await q.message.reply_text(
            f"{text}\nTotal RM{total}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Confirm", callback_data="confirm")]
            ])
        )

    elif data == "confirm":
        cart = user_cart[chat_id]

        text = "\n".join([x["name"] for x in cart])
        total = sum(x["price"] for x in cart)

        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"ORDER\n{text}\nTotal RM{total}"
        )

        await q.message.reply_text("Order hantar ✅")
        user_cart[chat_id] = []

# =========================
# CHAT (AI + MENU)
# =========================
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text in ["menu", "order"]:
        await menu(update, context)
        return

    reply = ask_ai(update.effective_user.id, update.message.text)
    await update.message.reply_text(reply)

# =========================
# MAIN
# =========================
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("id", get_id))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

app.run_polling()
