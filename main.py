#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
import json
import sqlite3
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from contextlib import contextmanager

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# حالت‌های مکالمه
WAITING_TOKEN, WAITING_OWNER_ID = range(2)

# ==================== دیتابیس ====================

@contextmanager
def get_db_connection():
    """مدیریت اتصال به دیتابیس"""
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
    """ایجاد جداول دیتابیس"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # جدول ربات‌ها
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            owner_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        )
        ''')
        
        # جدول کاربران
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            country TEXT NOT NULL DEFAULT 'ایران 🇮🇷',
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_owner BOOLEAN DEFAULT FALSE,
            resources TEXT DEFAULT '{"money": 10000, "oil": 500, "electricity": 1000, "population": 1000}',
            units TEXT DEFAULT '{}',
            technology_level INTEGER DEFAULT 1,
            morale INTEGER DEFAULT 100,
            last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, bot_id)
        )
        ''')
        
        # جدول وام‌ها
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            remaining INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # جدول نیروها
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            unit_type TEXT NOT NULL,
            unit_name TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1
        )
        ''')

init_database()

# ==================== توابع کمکی ====================

def get_default_units():
    """واحدهای پیش‌فرض بازی"""
    return {
        "ground": [
            {"name": "تازه نفس 👶", "count": 10, "cost": 50},
            {"name": "ارپیجی زن 🚀", "count": 5, "cost": 200},
            {"name": "تک تیرانداز ⛺", "count": 5, "cost": 150},
            {"name": "سرباز حرفه ای 🪖", "count": 0, "cost": 300}
        ],
        "air": [
            {"name": "موشک کوتاه‌برد", "count": 2, "cost": 500},
            {"name": "جنگنده سبک", "count": 1, "cost": 1000}
        ],
        "defense": [
            {"name": "پدافند معمولی 📡", "count": 3, "cost": 400},
            {"name": "پدافند حرفه ای 📡", "count": 0, "cost": 800}
        ]
    }

def get_default_resources():
    """منابع پیش‌فرض"""
    return {
        "money": 10000,
        "oil": 500,
        "electricity": 1000,
        "population": 1000
    }

# ==================== ربات مادر ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ربات مادر"""
    user = update.effective_user
    await update.message.reply_text(
        f"👑 سلام {user.first_name}!\n"
        f"به ربات مادر بازی استراتژیک خوش آمدید.\n\n"
        f"📋 دستورات:\n"
        f"/addbot - ایجاد ربات فرزند جدید\n"
        f"/listbots - نمایش ربات‌های شما\n"
        f"/help - راهنمای کامل"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """راهنمای ربات مادر"""
    help_text = (
        "📚 **راهنمای ربات مادر**\n\n"
        "🛠 **دستورات:**\n"
        "• /start - شروع ربات\n"
        "• /addbot - ایجاد ربات فرزند\n"
        "• /listbots - نمایش ربات‌ها\n"
        "• /help - این راهنما\n\n"
        "⚙️ **نحوه کار:**\n"
        "1. با /addbot ربات فرزند بسازید\n"
        "2. توکن را از @BotFather بگیرید\n"
        "3. آیدی عددی خود را وارد کنید\n"
        "4. بازی شروع می‌شود!"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def list_bots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست ربات‌های کاربر"""
    user_id = update.effective_user.id
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, created_at, status FROM bots WHERE owner_id = ?",
            (user_id,)
        )
        bots = cursor.fetchall()
    
    if not bots:
        await update.message.reply_text("🤖 شما هیچ ربات فرزندی ندارید.")
        return
    
    message = "📋 **ربات‌های شما:**\n\n"
    for bot in bots:
        message += f"🔹 ربات #{bot['id']}\n📅 {bot['created_at'][:10]}\n🟢 {bot['status']}\n\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def add_bot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع فرآیند افزودن ربات"""
    await update.message.reply_text(
        "🤖 **ایجاد ربات فرزند:**\n\n"
        "1. به @BotFather بروید\n"
        "2. /newbot را بزنید\n"
        "3. نام و یوزرنیم انتخاب کنید\n"
        "4. توکن را کپی کنید\n\n"
        "✅ لطفاً توکن را ارسال کنید:"
    )
    return WAITING_TOKEN

async def process_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش توکن"""
    token = update.message.text.strip()
    
    if not token.startswith('') or ':' not in token:
        await update.message.reply_text("❌ توکن نامعتبر! دوباره ارسال کنید:")
        return WAITING_TOKEN
    
    context.user_data['bot_token'] = token
    
    await update.message.reply_text(
        "✅ توکن دریافت شد!\n\n"
        "🔢 آیدی عددی خود را ارسال کنید:\n"
        "(از @userinfobot دریافت کنید)"
    )
    return WAITING_OWNER_ID

async def process_owner_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش آیدی مالک"""
    try:
        owner_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ آیدی باید عدد باشد! دوباره ارسال کنید:")
        return WAITING_OWNER_ID
    
    token = context.user_data.get('bot_token')
    user = update.effective_user
    
    if not token:
        await update.message.reply_text("❌ خطا! /addbot را دوباره بزنید.")
        return ConversationHandler.END
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO bots (token, owner_id) VALUES (?, ?)",
                (token, owner_id)
            )
            bot_id = cursor.lastrowid
            
            # ایجاد ربات فرزند
            child_bot_token = token
            # در اینجا باید ربات فرزند را راه‌اندازی کنیم
            # اما فعلاً فقط دیتابیس را پر می‌کنیم
            
            await update.message.reply_text(
                f"🎉 **ربات ایجاد شد!**\n\n"
                f"🔑 شناسه: `{bot_id}`\n"
                f"👤 مالک: {owner_id}\n\n"
                f"✅ اکنون می‌توانید بازی کنید!",
                parse_mode='Markdown'
            )
            
            if 'bot_token' in context.user_data:
                del context.user_data['bot_token']
            
            return ConversationHandler.END
            
        except sqlite3.IntegrityError:
            await update.message.reply_text("❌ توکن تکراری! توکن جدیدی ارسال کنید:")
            return WAITING_TOKEN
        except Exception as e:
            logger.error(f"خطا: {e}")
            await update.message.reply_text(f"❌ خطا: {str(e)}")
            return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو فرآیند"""
    if 'bot_token' in context.user_data:
        del context.user_data['bot_token']
    
    await update.message.reply_text("❌ عملیات لغو شد.")
    return ConversationHandler.END

# ==================== ربات فرزند ====================

def create_child_app(token: str, bot_id: int):
    """ایجاد اپلیکیشن ربات فرزند"""
    app = Application.builder().token(token).build()
    
    # ثبت هندلرها
    app.add_handler(CommandHandler("start", child_start))
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CommandHandler("help", child_help))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    return app

async def child_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ربات فرزند"""
    user = update.effective_user
    user_id = user.id
    
    # استخراج bot_id از context
    bot_id = getattr(context, 'bot_id', 1)  # مقدار پیش‌فرض
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # بررسی کاربر موجود
        cursor.execute(
            "SELECT * FROM users WHERE user_id = ? AND bot_id = ?",
            (user_id, bot_id)
        )
        user_data = cursor.fetchone()
        
        if user_data:
            # کاربر موجود
            await show_welcome_back(update, user_data)
        else:
            # کاربر جدید - ایجاد پروفایل
            default_resources = json.dumps(get_default_resources())
            default_units = json.dumps(get_default_units())
            
            cursor.execute(
                """INSERT INTO users 
                (user_id, bot_id, username, first_name, last_name, resources, units)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, bot_id, user.username, user.first_name, 
                 user.last_name or "", default_resources, default_units)
            )
            
            await show_welcome_new(update)

async def show_welcome_back(update: Update, user_data):
    """خوش آمدگویی به کاربر قدیمی"""
    resources = json.loads(user_data['resources'])
    
    keyboard = [
        [
            InlineKeyboardButton("🪖 نیروها", callback_data="menu_units"),
            InlineKeyboardButton("💰 منابع", callback_data="menu_resources")
        ],
        [
            InlineKeyboardButton("⚔️ حمله", callback_data="menu_attack"),
            InlineKeyboardButton("👤 پروفایل", callback_data="menu_profile")
        ],
        [
            InlineKeyboardButton("💵 وام", callback_data="menu_loan"),
            InlineKeyboardButton("📘 راهنما", callback_data="menu_help")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎖 **خوش آمدید!**\n\n"
        f"💰 موجودی: {resources['money']:,}\n"
        f"🛢 نفت: {resources['oil']:,}\n"
        f"⚡ برق: {resources['electricity']:,}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_welcome_new(update: Update):
    """خوش آمدگویی به کاربر جدید"""
    keyboard = [
        [
            InlineKeyboardButton("🎮 شروع بازی", callback_data="start_game")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎉 **به بازی استراتژیک خوش آمدید!**\n\n"
        "شما رهبر یک کشور جدید هستید.\n"
        "برای شروع روی دکمه زیر کلیک کنید.",
        reply_markup=reply_markup
    )

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی اصلی"""
    keyboard = [
        [
            InlineKeyboardButton("🪖 نیروها", callback_data="menu_units"),
            InlineKeyboardButton("💰 منابع", callback_data="menu_resources")
        ],
        [
            InlineKeyboardButton("⚔️ حمله", callback_data="menu_attack"),
            InlineKeyboardButton("👤 پروفایل", callback_data="menu_profile")
        ],
        [
            InlineKeyboardButton("💵 وام", callback_data="menu_loan"),
            InlineKeyboardButton("📘 راهنما", callback_data="menu_help")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🏰 **منوی اصلی بازی**\n\n"
        "لطفاً گزینه مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def child_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """راهنمای ربات فرزند"""
    help_text = (
        "🎮 **راهنمای بازی**\n\n"
        "🪖 **نیروها:** انواع سرباز، هواپیما، پدافند\n"
        "💰 **منابع:** پول، نفت، برق، جمعیت\n"
        "⚔️ **حمله:** به کشورهای دیگر حمله کنید\n"
        "💵 **وام:** روزی یک بار دریافت کنید\n\n"
        "📱 **دستورات:**\n"
        "/start - شروع بازی\n"
        "/menu - منوی اصلی\n"
        "/help - این راهنما"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت کلیک روی دکمه‌ها"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "start_game":
        await start_game(query)
    elif data == "menu_units":
        await show_units_menu(query)
    elif data == "menu_resources":
        await show_resources_menu(query)
    elif data == "menu_profile":
        await show_profile_menu(query)
    elif data == "menu_loan":
        await show_loan_menu(query)
    elif data == "menu_help":
        await show_help_menu(query)

async def start_game(query):
    """شروع بازی"""
    keyboard = [
        [InlineKeyboardButton("🏰 منوی اصلی", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎮 **بازی شروع شد!**\n\n"
        "منابع اولیه به شما تعلق گرفت.\n"
        "از منوی اصلی برای پیشرفت استفاده کنید.",
        reply_markup=reply_markup
    )

async def show_units_menu(query):
    """نمایش منوی نیروها"""
    user_id = query.from_user.id
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT units FROM users WHERE user_id = ?",
            (user_id,)
        )
        user_data = cursor.fetchone()
    
    if user_data:
        units = json.loads(user_data['units'])
        
        message = "🪖 **نیروهای شما:**\n\n"
        
        for category, unit_list in units.items():
            message += f"**{category.upper()}:**\n"
            for unit in unit_list:
                message += f"• {unit['name']}: {unit['count']} عدد\n"
            message += "\n"
    
    else:
        message = "❌ اطلاعات یافت نشد!"
    
    keyboard = [
        [InlineKeyboardButton("⬆️ افزایش نیرو", callback_data="upgrade_units")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_resources_menu(query):
    """نمایش منوی منابع"""
    user_id = query.from_user.id
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT resources FROM users WHERE user_id = ?",
            (user_id,)
        )
        user_data = cursor.fetchone()
    
    if user_data:
        resources = json.loads(user_data['resources'])
        
        message = (
            "💰 **منابع شما:**\n\n"
            f"• پول: {resources.get('money', 0):,}\n"
            f"• نفت: {resources.get('oil', 0):,}\n"
            f"• برق: {resources.get('electricity', 0):,}\n"
            f"• جمعیت: {resources.get('population', 0):,}\n\n"
            f"📈 **درآمد:**\n"
            f"• کارخانه: +1000 پول/روز\n"
            f"• معدن: +500 نفت/روز"
        )
    else:
        message = "❌ اطلاعات یافت نشد!"
    
    keyboard = [
        [InlineKeyboardButton("🏭 ساخت سازه", callback_data="build_structure")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_profile_menu(query):
    """نمایش پروفایل"""
    user_id = query.from_user.id
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT country, resources, technology_level, morale FROM users WHERE user_id = ?",
            (user_id,)
        )
        user_data = cursor.fetchone()
    
    if user_data:
        resources = json.loads(user_data['resources'])
        
        message = (
            f"👤 **پروفایل کشور {user_data['country']}**\n\n"
            f"💰 پول: {resources.get('money', 0):,}\n"
            f"🧠 تکنولوژی: سطح {user_data['technology_level']}\n"
            f"😊 روحیه: {user_data['morale']}%\n\n"
            f"🏆 **آمار:**\n"
            f"• نیروها: در حال محاسبه...\n"
            f"• سازه‌ها: 5 عدد\n"
            f"• رتبه: #--"
        )
    else:
        message = "❌ اطلاعات یافت نشد!"
    
    keyboard = [
        [InlineKeyboardButton("🔄 به‌روزرسانی", callback_data="refresh_profile")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_loan_menu(query):
    """نمایش منوی وام"""
    user_id = query.from_user.id
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # بررسی وام قبلی
        cursor.execute(
            "SELECT created_at FROM loans WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        last_loan = cursor.fetchone()
        
        cursor.execute(
            "SELECT resources FROM users WHERE user_id = ?",
            (user_id,)
        )
        user_resources = cursor.fetchone()
    
    can_get_loan = True
    if last_loan:
        last_date = datetime.fromisoformat(last_loan['created_at'])
        if datetime.now() - last_date < timedelta(hours=24):
            can_get_loan = False
    
    resources = json.loads(user_resources['resources']) if user_resources else {}
    
    if can_get_loan:
        message = (
            "💵 **دریافت وام**\n\n"
            f"💰 موجودی: {resources.get('money', 0):,}\n\n"
            "📋 **شرایط:**\n"
            "• حداکثر: ۵٬۰۰۰ پول\n"
            "• بازپرداخت: ۲۴ ساعت\n"
            "• سود: ۱۰٪\n"
            "• یک بار در روز\n\n"
            "✅ قابل دریافت"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("💵 وام ۲۰۰۰", callback_data="loan_2000"),
                InlineKeyboardButton("💵 وام ۵۰۰۰", callback_data="loan_5000")
            ],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]
        ]
    else:
        message = (
            "💵 **وضعیت وام**\n\n"
            f"📅 آخرین وام: {last_loan['created_at'][:10]}\n\n"
            "⏰ می‌توانید ۲۴ ساعت پس از آخرین وام، مجدداً دریافت کنید."
        )
        
        keyboard = [[InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_help_menu(query):
    """نمایش راهنمای بازی"""
    help_text = (
        "📘 **راهنمای بازی استراتژیک**\n\n"
        
        "🎯 **هدف:**\n"
        "• توسعه کشور خود\n"
        "• تقویت نیروها\n"
        "• حمله به دیگران\n"
        "• تبدیل به ابرقدرت\n\n"
        
        "⚔️ **نیروها:**\n"
        "• زمینی: سرباز، توپخانه\n"
        "• هوایی: جنگنده، موشک\n"
        "• دریایی: کشتی، زیردریایی\n"
        "• سایبری: هکر، تیم هک\n\n"
        
        "💰 **اقتصاد:**\n"
        "• منابع: پول، نفت، برق\n"
        "• سازه‌ها: کارخانه، معدن\n"
        "• وام: روزی یک بار\n\n"
        
        "🏆 **پیروزی:**\n"
        "• فتح تمام کشورها\n"
        "• یا قوی‌ترین پس از ۳۰ روز"
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        help_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ==================== اجرای اصلی ====================

def main():
    """تابع اصلی"""
    
    # دریافت توکن از متغیر محیطی
    MOTHER_TOKEN = os.getenv("MOTHER_BOT_TOKEN")
    
    if not MOTHER_TOKEN:
        logger.error("❌ MOTHER_BOT_TOKEN تنظیم نشده!")
        logger.info("لطفاً در Render.com متغیر زیر را تنظیم کنید:")
        logger.info("MOTHER_BOT_TOKEN: توکن ربات مادر از @BotFather")
        return
    
    # ایجاد اپلیکیشن ربات مادر
    mother_app = Application.builder().token(MOTHER_TOKEN).build()
    
    # تنظیم هندلرهای ربات مادر
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('addbot', add_bot_start)],
        states={
            WAITING_TOKEN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_token)
            ],
            WAITING_OWNER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_owner_id)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    mother_app.add_handler(conv_handler)
    mother_app.add_handler(CommandHandler('start', start))
    mother_app.add_handler(CommandHandler('listbots', list_bots_command))
    mother_app.add_handler(CommandHandler('help', help_command))
    
    # راه‌اندازی ربات مادر
    logger.info("🚀 ربات مادر در حال راه‌اندازی...")
    
    # بررسی حالت اجرا
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
    PORT = int(os.getenv("PORT", 8443))
    
    if WEBHOOK_URL:
        # حالت وب‌هوک برای Render
        logger.info(f"📡 استفاده از وب‌هوک: {WEBHOOK_URL}")
        
        # اجرا با وب‌هوک
        mother_app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{WEBHOOK_URL}/webhook",
            drop_pending_updates=True
        )
    else:
        # حالت توسعه با polling
        logger.info("🔧 حالت توسعه (polling)")
        mother_app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    # اجرای برنامه
    try:
        main()
    except KeyboardInterrupt:
        logger.info("👋 ربات متوقف شد.")
    except Exception as e:
        logger.error(f"❌ خطا: {e}")
        import traceback
        logger.error(traceback.format_exc())
