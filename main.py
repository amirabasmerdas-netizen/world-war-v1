#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
import json
import sqlite3
from datetime import datetime
from contextlib import contextmanager

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor

# تنظیمات لاگ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# حالت‌های مکالمه
class Form(StatesGroup):
    waiting_token = State()
    waiting_owner_id = State()

# ==================== دیتابیس ====================

@contextmanager
def get_db_connection():
    conn = sqlite3.connect('war_game.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_database():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            owner_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            resources TEXT DEFAULT '{"money": 10000}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

init_database()

# ==================== ربات ====================

# دریافت توکن
MOTHER_TOKEN = os.getenv("MOTHER_BOT_TOKEN")
if not MOTHER_TOKEN:
    raise ValueError("MOTHER_BOT_TOKEN not set!")

bot = Bot(token=MOTHER_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# ==================== هندلرها ====================

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.reply(
        f"👑 سلام {message.from_user.first_name}!\n"
        f"به ربات مادر بازی استراتژیک خوش آمدید.\n\n"
        f"📋 دستورات:\n"
        f"/addbot - ایجاد ربات فرزند\n"
        f"/listbots - نمایش ربات‌ها\n"
        f"/help - راهنمای کامل"
    )

@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    await message.reply(
        "📚 راهنمای ربات مادر\n\n"
        "🛠 دستورات:\n"
        "• /start - شروع ربات\n"
        "• /addbot - ایجاد ربات فرزند\n"
        "• /listbots - نمایش ربات‌ها\n"
        "• /help - این راهنما"
    )

@dp.message_handler(commands=['listbots'])
async def cmd_listbots(message: types.Message):
    user_id = message.from_user.id
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, created_at FROM bots WHERE owner_id = ?",
            (user_id,)
        )
        bots = cursor.fetchall()
    
    if not bots:
        await message.reply("🤖 شما هیچ ربات فرزندی ندارید.")
        return
    
    text = "📋 ربات‌های شما:\n\n"
    for bot_row in bots:
        text += f"🔹 ربات #{bot_row['id']}\n📅 {bot_row['created_at'][:10]}\n\n"
    
    await message.reply(text)

@dp.message_handler(commands=['addbot'])
async def cmd_addbot(message: types.Message):
    await Form.waiting_token.set()
    await message.reply(
        "🤖 لطفاً توکن ربات فرزند را ارسال کنید:\n"
        "(از @BotFather دریافت کنید)"
    )

@dp.message_handler(state=Form.waiting_token)
async def process_token(message: types.Message, state: FSMContext):
    token = message.text.strip()
    
    if ':' not in token:
        await message.reply("❌ توکن نامعتبر! دوباره ارسال کنید:")
        return
    
    await state.update_data(token=token)
    await Form.next()
    await message.reply(
        "✅ توکن دریافت شد!\n\n"
        "🔢 آیدی عددی خود را ارسال کنید:"
    )

@dp.message_handler(state=Form.waiting_owner_id)
async def process_owner_id(message: types.Message, state: FSMContext):
    try:
        owner_id = int(message.text.strip())
    except ValueError:
        await message.reply("❌ آیدی باید عدد باشد! دوباره ارسال کنید:")
        return
    
    data = await state.get_data()
    token = data.get('token')
    
    if not token:
        await message.reply("❌ خطا! دوباره /addbot را بزنید.")
        await state.finish()
        return
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO bots (token, owner_id) VALUES (?, ?)",
                (token, owner_id)
            )
            bot_id = cursor.lastrowid
            
            await message.reply(
                f"🎉 ربات ایجاد شد!\n\n"
                f"🔑 شناسه: {bot_id}\n"
                f"👤 مالک: {owner_id}\n\n"
                f"✅ اکنون می‌توانید بازی کنید!"
            )
            
        except sqlite3.IntegrityError:
            await message.reply("❌ این توکن قبلاً ثبت شده است!")
        except Exception as e:
            logger.error(f"خطا: {e}")
            await message.reply(f"❌ خطا: {str(e)}")
    
    await state.finish()

# ==================== اجرا ====================

async def on_startup(dp):
    logger.info("🚀 ربات مادر شروع به کار کرد")

async def on_shutdown(dp):
    logger.info("👋 ربات مادر متوقف شد")

if __name__ == '__main__':
    # بررسی وب‌هوک
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
    PORT = int(os.getenv("PORT", 8443))
    
    if WEBHOOK_URL:
        # حالت وب‌هوک برای Render
        from aiogram.utils.executor import start_webhook
        
        async def on_startup_webhook(dp):
            await bot.set_webhook(f"{WEBHOOK_URL}/webhook")
            logger.info(f"Webhook set to: {WEBHOOK_URL}/webhook")
        
        start_webhook(
            dispatcher=dp,
            webhook_path='/webhook',
            on_startup=on_startup_webhook,
            on_shutdown=on_shutdown,
            skip_updates=True,
            host='0.0.0.0',
            port=PORT
        )
    else:
        # حالت توسعه
        executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
