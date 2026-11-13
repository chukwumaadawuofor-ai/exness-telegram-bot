import os
import hmac
import hashlib
import time
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load Environment Variables from Railway
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_CHAT_ID = int(os.getenv("ALLOWED_CHAT_ID", "0"))
EXNESS_API_KEY = os.getenv("EXNESS_API_KEY")
EXNESS_API_SECRET = os.getenv("EXNESS_API_SECRET")
EXNESS_BASE_URL = os.getenv("EXNESS_BASE_URL", "https://api.exness.com/v1")
EXNESS_ACCOUNT_ID = os.getenv("EXNESS_ACCOUNT_ID")

# Bot State
bot_active = True
SYMBOL = "EURUSD"
LOT_SIZE = 0.01

def generate_signature(method: str, path: str, timestamp: str, body: str = "") -> str:
    """Generates HMAC-SHA256 signature required by Exness API authentication."""
    message = f"{method}\n{path}\n{timestamp}\n{body}"
    signature = hmac.new(
        EXNESS_API_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return signature

def exness_request(method: str, endpoint: str, payload: dict = None):
    """Executes authenticated HTTP requests to Exness API."""
    import json
    url = f"{EXNESS_BASE_URL}{endpoint}"
    timestamp = str(int(time.time() * 1000))
    body_str = json.dumps(payload) if payload else ""
    signature = generate_signature(method, endpoint, timestamp, body_str)
    
    headers = {
        "Content-Type": "application/json",
        "ApiKey": EXNESS_API_KEY,
        "Timestamp": timestamp,
        "Signature": signature
    }
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=headers, data=body_str, timeout=10)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, timeout=10)
        else:
            return None
        return response.json()
    except Exception as e:
        logger.error(f"Exness API error on {endpoint}: {e}")
        return None

# --- TELEGRAM COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    await update.message.reply_text(
        "🤖 *Exness Trading Bot Online*\n\n"
        "Commands available:\n"
        "/status - Check bot connection & loop state\n"
        "/balance - View account balance & margin\n"
        "/positions - View active open trades\n"
        "/pause - Pause automated trading\n"
        "/resume - Resume automated trading\n"
        "/closeall - Emergency close all positions",
        parse_mode="Markdown"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    state = "🟢 ACTIVE (Scanning markets)" if bot_active else "🔴 PAUSED"
    await update.message.reply_text(f"Bot Status: {state}\nSymbol: {SYMBOL}\nLot Size: {LOT_SIZE}")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    res = exness_request("GET", f"/accounts/{EXNESS_ACCOUNT_ID}")
    if res and "balance" in res:
        bal = res["balance"]
        equity = res.get("equity", bal)
        currency = res.get("currency", "NGN")
        await update.message.reply_text(f"💰 *Account Balance:* {bal} {currency}\n📈 *Equity:* {equity} {currency}", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Could not fetch account balance from Exness API.")

async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    res = exness_request("GET", f"/accounts/{EXNESS_ACCOUNT_ID}/positions")
    if res and isinstance(res, list):
        if not res:
            await update.message.reply_text("📂 No open positions currently.")
            return
        msg = "📂 *Active Positions:*\n"
        for p in res:
            msg += f"- {p.get('symbol')} {p.get('type')} {p.get('volume')} lots @ {p.get('price_open')}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Could not retrieve open positions.")

async def pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    bot_active = False
    await update.message.reply_text("⏸️ Automated trading paused.")

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    bot_active = True
    await update.message.reply_text("▶️ Automated trading resumed.")

async def close_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    res = exness_request("GET", f"/accounts/{EXNESS_ACCOUNT_ID}/positions")
    if res and isinstance(res, list):
        count = 0
        for p in res:
            pos_id = p.get("id")
            exness_request("DELETE", f"/accounts/{EXNESS_ACCOUNT_ID}/positions/{pos_id}")
            count += 1
        await update.message.reply_text(f"🛑 Emergency closed {count} open position(s).")
    else:
        await update.message.reply_text("⚠️ No positions to close or error connecting.")

def main():
    # Build Telegram Application
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("positions", positions))
    app.add_handler(CommandHandler("pause", pause_bot))
    app.add_handler(CommandHandler("resume", resume_bot))
    app.add_handler(CommandHandler("closeall", close_all))

    logger.info("Starting Telegram & Exness Trading Bot listener...")
    app.run_polling()

if __name__ == "__main__":
    main()
