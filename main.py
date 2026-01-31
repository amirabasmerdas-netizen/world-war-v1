#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
import asyncio
import json
import sqlite3
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
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
WAITING_TOKEN, WAITING_OWNER_ID, WAITING_COUNTRY = range(3)

# ==================== کلاس دیتابیس ====================

class DatabaseManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.init_database()
        return cls._instance
    
    def init_database(self):
        """ایجاد جداول دیتابیس"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # جدول ربات‌ها
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                owner_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active',
                webhook_url TEXT
            )
            ''')
            
            # جدول کاربران
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                bot_id INTEGER NOT NULL,
                country TEXT NOT NULL,
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
            
            # جدول AI کشورها
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_countries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                personality TEXT DEFAULT 'neutral',
                strategy TEXT DEFAULT '{}',
                resources TEXT DEFAULT '{"money": 15000, "oil": 800, "electricity": 1200, "population": 1500}',
                units TEXT DEFAULT '{}',
                technology_level INTEGER DEFAULT 1,
                morale INTEGER DEFAULT 100,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # جدول جنگ‌ها
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS battles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER NOT NULL,
                attacker_id INTEGER,
                defender_id INTEGER,
                attacker_type TEXT CHECK(attacker_type IN ('player', 'ai')),
                defender_type TEXT CHECK(defender_type IN ('player', 'ai')),
                attacker_country TEXT,
                defender_country TEXT,
                units_used TEXT,
                result TEXT,
                loot TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                last_payment_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # جدول اتحادها
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS alliances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                leader_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # جدول اعضای اتحاد
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS alliance_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alliance_id INTEGER NOT NULL,
                user_id INTEGER,
                ai_id INTEGER,
                member_type TEXT CHECK(member_type IN ('player', 'ai')),
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (alliance_id) REFERENCES alliances(id)
            )
            ''')
            
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """مدیریت اتصال به دیتابیس"""
        conn = sqlite3.connect('war_game.db', check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

db = DatabaseManager()

# ==================== کلاس اصلی ربات مادر ====================

class MotherBot:
    def __init__(self, token: str):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """تنظیم هندلرهای ربات مادر"""
        
        # هندلر برای ثبت ربات جدید
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('addbot', self.start_add_bot)],
            states={
                WAITING_TOKEN: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_bot_token)
                ],
                WAITING_OWNER_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_owner_id)
                ],
            },
            fallbacks=[CommandHandler('cancel', self.cancel_add_bot)]
        )
        
        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler('start', self.mother_start))
        self.application.add_handler(CommandHandler('listbots', self.list_bots))
        self.application.add_handler(CommandHandler('help', self.mother_help))
        self.application.add_handler(CallbackQueryHandler(self.handle_mother_callback))
    
    async def mother_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع ربات مادر"""
        user = update.effective_user
        await update.message.reply_text(
            f"👑 سلام {user.first_name}!\n"
            f"به ربات مادر بازی استراتژیک خوش آمدید.\n\n"
            f"شما می‌توانید چندین ربات فرزند ایجاد و مدیریت کنید.\n\n"
            f"📋 دستورات اصلی:\n"
            f"/addbot - ایجاد ربات فرزند جدید\n"
            f"/listbots - مشاهده ربات‌های شما\n"
            f"/help - راهنمای کامل"
        )
    
    async def start_add_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع فرآیند افزودن ربات"""
        await update.message.reply_text(
            "🤖 **مراحل ایجاد ربات فرزند:**\n\n"
            "1. به @BotFather مراجعه کنید\n"
            "2. روی /newbot کلیک کنید\n"
            "3. یک نام برای ربات انتخاب کنید\n"
            "4. یک یوزرنیم منحصربه‌فرد انتخاب کنید\n"
            "5. توکن ربات را کپی کنید\n\n"
            "✅ لطفاً توکن ربات را ارسال کنید:"
        )
        return WAITING_TOKEN
    
    async def process_bot_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش توکن ربات"""
        token = update.message.text.strip()
        
        # بررسی فرمت توکن
        if not token.startswith('') or ':' not in token:
            await update.message.reply_text(
                "❌ توکن نامعتبر است!\n"
                "لطفاً یک توکن معتبر از @BotFather ارسال کنید:"
            )
            return WAITING_TOKEN
        
        context.user_data['bot_token'] = token
        
        await update.message.reply_text(
            "✅ توکن دریافت شد!\n\n"
            "🔢 حالا آیدی عددی خود را ارسال کنید:\n"
            "(برای دریافت آیدی عددی به @userinfobot مراجعه کنید)"
        )
        return WAITING_OWNER_ID
    
    async def process_owner_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش آیدی مالک"""
        try:
            owner_id = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text(
                "❌ آیدی باید یک عدد باشد!\n"
                "لطفاً آیدی عددی خود را ارسال کنید:"
            )
            return WAITING_OWNER_ID
        
        token = context.user_data.get('bot_token')
        user_id = update.effective_user.id
        
        # ذخیره در دیتابیس
        with db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO bots (token, owner_id) VALUES (?, ?)",
                    (token, owner_id)
                )
                bot_id = cursor.lastrowid
                
                # ایجاد ربات فرزند
                child_bot = ChildBot(token, bot_id)
                
                # ساختار پیش‌فرض برای مالک
                default_resources = {
                    'money': 20000,
                    'oil': 1000,
                    'electricity': 1500,
                    'population': 2000
                }
                
                default_units = json.dumps(child_bot.get_default_units())
                
                cursor.execute(
                    """INSERT INTO users 
                    (user_id, bot_id, country, username, first_name, last_name, is_owner, resources, units)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (owner_id, bot_id, "ایران 🇮🇷", update.effective_user.username,
                     update.effective_user.first_name, update.effective_user.last_name,
                     True, json.dumps(default_resources), default_units)
                )
                
                # ایجاد کشورهای AI پیش‌فرض
                self.create_default_ai_countries(bot_id, conn)
                
                await update.message.reply_text(
                    f"🎉 **ربات فرزند با موفقیت ایجاد شد!**\n\n"
                    f"🔑 شناسه ربات: `{bot_id}`\n"
                    f"👤 مالک: آیدی {owner_id}\n"
                    f"🤖 ربات: @{update.effective_user.username}\n\n"
                    f"✅ اکنون می‌توانید به ربات فرزند مراجعه کنید و شروع به بازی کنید!"
                )
                
                # پاک کردن داده‌های موقت
                if 'bot_token' in context.user_data:
                    del context.user_data['bot_token']
                
                return ConversationHandler.END
                
            except sqlite3.IntegrityError:
                await update.message.reply_text(
                    "❌ این توکن قبلاً ثبت شده است!\n"
                    "لطفاً توکن جدیدی ارسال کنید:"
                )
                return WAITING_TOKEN
    
    def create_default_ai_countries(self, bot_id: int, conn):
        """ایجاد کشورهای AI پیش‌فرض"""
        cursor = conn.cursor()
        
        ai_countries = [
            ("آمریکا 🤖", "aggressive", {"money": 25000, "oil": 1500, "electricity": 2000, "population": 2500}),
            ("روسیه 🤖", "unpredictable", {"money": 22000, "oil": 1800, "electricity": 1800, "population": 2200}),
            ("چین 🤖", "defensive", {"money": 23000, "oil": 1600, "electricity": 1900, "population": 3000}),
            ("آلمان 🤖", "neutral", {"money": 20000, "oil": 1200, "electricity": 1700, "population": 1800}),
            ("ژاپن 🤖", "strategic", {"money": 21000, "oil": 1000, "electricity": 1600, "population": 1700}),
        ]
        
        for name, personality, resources in ai_countries:
            cursor.execute(
                """INSERT INTO ai_countries 
                (bot_id, name, personality, resources) 
                VALUES (?, ?, ?, ?)""",
                (bot_id, name, personality, json.dumps(resources))
            )
    
    async def cancel_add_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو فرآیند افزودن ربات"""
        if 'bot_token' in context.user_data:
            del context.user_data['bot_token']
        
        await update.message.reply_text("❌ فرآیند ایجاد ربات لغو شد.")
        return ConversationHandler.END
    
    async def list_bots(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لیست ربات‌های کاربر"""
        user_id = update.effective_user.id
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, token, created_at, status FROM bots WHERE owner_id = ?",
                (user_id,)
            )
            bots = cursor.fetchall()
        
        if not bots:
            await update.message.reply_text("🤖 شما هنوز هیچ ربات فرزندی ندارید.")
            return
        
        message = "📋 **ربات‌های فرزند شما:**\n\n"
        for bot in bots:
            message += (
                f"🔹 **ربات #{bot['id']}**\n"
                f"   📅 ایجاد: {bot['created_at']}\n"
                f"   🟢 وضعیت: {bot['status']}\n"
                f"   🔑 توکن: `{bot['token'][:15]}...`\n\n"
            )
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def mother_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """راهنمای ربات مادر"""
        help_text = (
            "📚 **راهنمای ربات مادر**\n\n"
            "🎯 **هدف:**\n"
            "مدیریت ربات‌های فرزند برای بازی استراتژیک\n\n"
            "🛠 **دستورات:**\n"
            "• /start - شروع ربات\n"
            "• /addbot - ایجاد ربات فرزند جدید\n"
            "• /listbots - نمایش ربات‌های شما\n"
            "• /help - این راهنما\n\n"
            "⚙️ **نحوه کار:**\n"
            "1. با /addbot یک ربات فرزند ایجاد کنید\n"
            "2. توکن ربات را از @BotFather دریافت کنید\n"
            "3. آیدی عددی خود را وارد کنید\n"
            "4. ربات فرزند آماده بازی است!\n\n"
            "❓ **پرسش‌های متداول:**\n"
            "Q: آیدی عددی چیست؟\n"
            "A: عددی منحصربه‌فرد شما در تلگرام (از @userinfobot دریافت کنید)\n\n"
            "Q: هر کاربر چند ربات می‌تواند داشته باشد؟\n"
            "A: محدودیتی وجود ندارد\n\n"
            "📞 پشتیبانی: @YourSupportChannel"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def handle_mother_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت کلیک روی دکمه‌های اینلاین"""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("این ویژگی در حال توسعه است...")

# ==================== کلاس ربات فرزند ====================

class ChildBot:
    def __init__(self, token: str, bot_id: int):
        self.token = token
        self.bot_id = bot_id
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
        
        # راه‌اندازی سیستم AI
        self.ai_system = AISystem(bot_id)
        
    def get_default_units(self):
        """واحدهای پیش‌فرض بازی"""
        return {
            "ground": {
                "تازه نفس 👶": 10,
                "ارپیجی زن 🚀": 60,
                "تک تیرانداز ⛺": 65,
                "سرباز حرفه ای 🪖": 1185,
                "توپخانه حرفه ای ⚽": 53,
                "سرباز 🙍‍♂️": 100,
                "توپخانه ⚽": 2
            },
            "air": {
                "موشک کوتاه‌برد": 5,
                "موشک میان‌برد": 3,
                "جنگنده سبک": 2,
                "جنگنده سنگین": 1
            },
            "defense": {
                "پدافند معمولی 📡": 5,
                "پدافند حرفه ای 📡": 312,
                "پدافند قدرتمند 📡": 100
            },
            "navy": {
                "ناو جنگی ⛴️": 2,
                "زیردریایی 💧": 3,
                "کشتی جنگی ⛵️": 5,
                "قایق جنگی 🚤": 10
            },
            "cyber": {
                "هکر حرفه ای 🧑‍💻": 2,
                "تیم هکری 👥": 1
            },
            "special": {
                "بمب هسته ای 🍄": 0,
                "بمب کوچولو 💣": 5
            },
            "factories": {
                "کارخانه ساده 🏚": 1,
                "کارخانه معمولی 🏭": 2,
                "کارخانه پیشرفته 🏢": 1
            },
            "infrastructure": {
                "بیمارستان 🏥": 1,
                "نیروگاه ⚡": 2,
                "مدرسه 🏫": 1
            }
        }
    
    def setup_handlers(self):
        """تنظیم هندلرهای ربات فرزند"""
        
        # هندلرهای اصلی
        self.application.add_handler(CommandHandler('start', self.child_start))
        self.application.add_handler(CommandHandler('help', self.child_help))
        self.application.add_handler(CommandHandler('menu', self.show_main_menu))
        
        # هندلر برای کلیک روی دکمه‌ها
        self.application.add_handler(CallbackQueryHandler(self.handle_child_callback))
        
        # هندلر برای پیام‌های متنی
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message)
        )
    
    async def child_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع ربات فرزند"""
        user = update.effective_user
        user_id = user.id
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # بررسی وجود کاربر
            cursor.execute(
                """SELECT u.*, b.owner_id 
                FROM users u 
                JOIN bots b ON u.bot_id = b.id 
                WHERE u.user_id = ? AND u.bot_id = ?""",
                (user_id, self.bot_id)
            )
            user_data = cursor.fetchone()
            
            if user_data:
                # کاربر موجود
                is_owner = user_data['user_id'] == user_data['owner_id']
                await self.show_welcome_back(update, user_data, is_owner)
            else:
                # کاربر جدید - بررسی آیا مالک است
                cursor.execute(
                    "SELECT owner_id FROM bots WHERE id = ?",
                    (self.bot_id,)
                )
                bot_data = cursor.fetchone()
                
                if bot_data and user_id == bot_data['owner_id']:
                    # مالک ربات
                    await self.show_owner_panel(update, user)
                else:
                    # کاربر عادی - انتخاب کشور
                    await self.show_country_selection(update, user_id)
    
    async def show_welcome_back(self, update: Update, user_data, is_owner: bool):
        """خوش آمدگویی به کاربر بازگشته"""
        country = user_data['country']
        resources = json.loads(user_data['resources'])
        
        if is_owner:
            message = f"👑 **خوش آمدید، فرمانده!**\n\n🏛 کشور: {country}\n💰 موجودی: {resources['money']:,}"
        else:
            message = f"🎖 **خوش آمدید!**\n\n🏛 کشور: {country}\n💰 موجودی: {resources['money']:,}"
        
        await update.message.reply_text(
            message,
            reply_markup=self.get_main_menu_keyboard(is_owner),
            parse_mode='Markdown'
        )
    
    async def show_owner_panel(self, update: Update, user):
        """نمایش پنل مالک"""
        keyboard = [
            [
                InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users"),
                InlineKeyboardButton("➕ کاربر جدید", callback_data="admin_add_user")
            ],
            [
                InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats"),
                InlineKeyboardButton("⚙️ تنظیمات", callback_data="admin_settings")
            ],
            [
                InlineKeyboardButton("🎮 شروع بازی", callback_data="start_game")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "👑 **پنل مدیریت ربات**\n\n"
            "شما مالک این ربات هستید. می‌توانید:\n"
            "• کاربران جدید اضافه کنید\n"
            "• آمار بازی را مشاهده کنید\n"
            "• تنظیمات را تغییر دهید\n\n"
            "برای شروع بازی روی 'شروع بازی' کلیک کنید.",
            reply_markup=reply_markup
        )
    
    async def show_country_selection(self, update: Update, user_id: int):
        """نمایش لیست کشورها برای انتخاب"""
        keyboard = [
            [
                InlineKeyboardButton("ایران 🇮🇷", callback_data="country_iran"),
                InlineKeyboardButton("عراق 🇮🇶", callback_data="country_iraq")
            ],
            [
                InlineKeyboardButton("ترکیه 🇹🇷", callback_data="country_turkey"),
                InlineKeyboardButton("عربستان 🇸🇦", callback_data="country_saudi")
            ],
            [
                InlineKeyboardButton("روسیه 🇷🇺", callback_data="country_russia"),
                InlineKeyboardButton("آمریکا 🇺🇸", callback_data="country_usa")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🏛 **انتخاب کشور**\n\n"
            "لطفاً کشور خود را انتخاب کنید:\n\n"
            "هر کشور مزایا و معایب خاص خود را دارد.",
            reply_markup=reply_markup
        )
    
    def get_main_menu_keyboard(self, is_owner: bool = False):
        """ایجاد کیبورد منوی اصلی"""
        keyboard = []
        
        if is_owner:
            # ردیف‌های مالک
            keyboard.append([
                InlineKeyboardButton("👥 مدیریت", callback_data="menu_admin"),
                InlineKeyboardButton("📊 آمار", callback_data="menu_stats")
            ])
        
        # ردیف‌های مشترک
        keyboard.extend([
            [
                InlineKeyboardButton("🪖 زمینی", callback_data="menu_ground"),
                InlineKeyboardButton("✈️ هوایی", callback_data="menu_air")
            ],
            [
                InlineKeyboardButton("📡 پدافند", callback_data="menu_defense"),
                InlineKeyboardButton("🚢 دریایی", callback_data="menu_navy")
            ],
            [
                InlineKeyboardButton("💻 سایبری", callback_data="menu_cyber"),
                InlineKeyboardButton("💣 ویژه", callback_data="menu_special")
            ],
            [
                InlineKeyboardButton("🏭 اقتصاد", callback_data="menu_economy"),
                InlineKeyboardButton("🏢 سازه‌ها", callback_data="menu_structures")
            ],
            [
                InlineKeyboardButton("🧠 تکنولوژی", callback_data="menu_tech"),
                InlineKeyboardButton("⚔️ حمله", callback_data="menu_attack")
            ],
            [
                InlineKeyboardButton("🏛 اتحاد", callback_data="menu_alliance"),
                InlineKeyboardButton("👤 اطلاعات", callback_data="menu_profile")
            ],
            [
                InlineKeyboardButton("📘 راهنما", callback_data="menu_guide"),
                InlineKeyboardButton("🛒 فروشگاه", callback_data="menu_shop")
            ],
            [
                InlineKeyboardButton("⚙️ تنظیمات", callback_data="menu_settings"),
                InlineKeyboardButton("💵 وام", callback_data="menu_loan")
            ]
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی اصلی"""
        user_id = update.effective_user.id
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT u.*, b.owner_id 
                FROM users u 
                JOIN bots b ON u.bot_id = b.id 
                WHERE u.user_id = ? AND u.bot_id = ?""",
                (user_id, self.bot_id)
            )
            user_data = cursor.fetchone()
        
        if user_data:
            is_owner = user_data['user_id'] == user_data['owner_id']
            country = user_data['country']
            
            await update.message.reply_text(
                f"🏰 **کشور {country}**\n\n"
                "منوی اصلی بازی:\n"
                "برای مدیریت نیروها و منابع از دکمه‌ها استفاده کنید.",
                reply_markup=self.get_main_menu_keyboard(is_owner),
                parse_mode='Markdown'
            )
    
    async def handle_child_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت کلیک روی دکمه‌های ربات فرزند"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        if data == "start_game":
            await self.start_new_game(query)
        
        elif data.startswith("country_"):
            country_code = data.split("_")[1]
            await self.assign_country(query, user_id, country_code)
        
        elif data.startswith("menu_"):
            menu_type = data.split("_")[1]
            await self.show_menu(query, menu_type)
        
        elif data == "menu_loan":
            await self.show_loan_menu(query)
        
        elif data == "get_loan":
            await self.process_loan_request(query)
    
    async def start_new_game(self, query):
        """شروع بازی جدید"""
        # ایجاد داده‌های اولیه بازی
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # به‌روزرسانی وضعیت کاربر
            cursor.execute(
                """UPDATE users 
                SET resources = ?, units = ?, technology_level = 1, morale = 100 
                WHERE user_id = ? AND bot_id = ?""",
                (
                    json.dumps({
                        "money": 10000,
                        "oil": 500,
                        "electricity": 1000,
                        "population": 1000
                    }),
                    json.dumps(self.get_default_units()),
                    query.from_user.id,
                    self.bot_id
                )
            )
            
            # بازنشانی کشورهای AI
            cursor.execute("DELETE FROM ai_countries WHERE bot_id = ?", (self.bot_id,))
            
            # ایجاد کشورهای AI جدید
            mother = MotherBot("")  # نمونه ساختگی
            mother.create_default_ai_countries(self.bot_id, conn)
        
        keyboard = [[InlineKeyboardButton("🏰 منوی اصلی", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎮 **بازی جدید شروع شد!**\n\n"
            "کشور شما با منابع اولیه ایجاد شد.\n"
            "کشورهای AI نیز آماده هستند.\n\n"
            "از منوی اصلی برای شروع استفاده کنید.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def assign_country(self, query, user_id: int, country_code: str):
        """اختصاص کشور به کاربر"""
        country_map = {
            "iran": "ایران 🇮🇷",
            "iraq": "عراق 🇮🇶",
            "turkey": "ترکیه 🇹🇷",
            "saudi": "عربستان 🇸🇦",
            "russia": "روسیه 🇷🇺",
            "usa": "آمریکا 🇺🇸"
        }
        
        country_name = country_map.get(country_code, "ایران 🇮🇷")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # ذخیره کاربر جدید
            default_resources = {
                'money': 10000,
                'oil': 500,
                'electricity': 1000,
                'population': 1000
            }
            
            cursor.execute(
                """INSERT INTO users 
                (user_id, bot_id, country, username, first_name, last_name, is_owner, resources, units)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    self.bot_id,
                    country_name,
                    query.from_user.username,
                    query.from_user.first_name,
                    query.from_user.last_name,
                    False,
                    json.dumps(default_resources),
                    json.dumps(self.get_default_units())
                )
            )
        
        await query.edit_message_text(
            f"✅ **کشور {country_name} انتخاب شد!**\n\n"
            f"به بازی استراتژیک خوش آمدید!\n"
            f"شما اکنون رهبر {country_name} هستید.\n\n"
            f"منابع اولیه به شما تعلق گرفت.",
            reply_markup=self.get_main_menu_keyboard(False),
            parse_mode='Markdown'
        )
    
    async def show_menu(self, query, menu_type: str):
        """نمایش منوهای مختلف"""
        user_id = query.from_user.id
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT resources, units, country FROM users WHERE user_id = ? AND bot_id = ?",
                (user_id, self.bot_id)
            )
            user_data = cursor.fetchone()
        
        if not user_data:
            await query.edit_message_text("❌ کاربر یافت نشد!")
            return
        
        resources = json.loads(user_data['resources'])
        units = json.loads(user_data['units'])
        country = user_data['country']
        
        if menu_type == "profile":
            await self.show_profile_menu(query, resources, units, country)
        
        elif menu_type == "ground":
            await self.show_ground_forces(query, units)
        
        elif menu_type == "economy":
            await self.show_economy_menu(query, resources)
        
        elif menu_type == "attack":
            await self.show_attack_menu(query, country)
        
        elif menu_type == "guide":
            await self.show_guide_menu(query)
    
    async def show_profile_menu(self, query, resources, units, country):
        """نمایش پروفایل کاربر"""
        total_troops = sum(sum(category.values()) for category in units.values() if isinstance(category, dict))
        
        message = (
            f"👤 **پروفایل کشور {country}**\n\n"
            f"💰 **منابع:**\n"
            f"  • پول: {resources.get('money', 0):,}\n"
            f"  • نفت: {resources.get('oil', 0):,}\n"
            f"  • برق: {resources.get('electricity', 0):,}\n"
            f"  • جمعیت: {resources.get('population', 0):,}\n\n"
            f"🎖 **نیروها:**\n"
            f"  • کل نیروها: {total_troops:,}\n"
            f"  • زمینی: {sum(units.get('ground', {}).values()):,}\n"
            f"  • هوایی: {sum(units.get('air', {}).values()):,}\n"
            f"  • دریایی: {sum(units.get('navy', {}).values()):,}\n\n"
            f"📈 **وضعیت:**\n"
            f"  • روحیه: 100%\n"
            f"  • تکنولوژی: سطح 1\n"
            f"  • رتبه: در حال محاسبه..."
        )
        
        keyboard = [
            [
                InlineKeyboardButton("📊 آمار کامل", callback_data="stats_full"),
                InlineKeyboardButton("🔄 به‌روزرسانی", callback_data="refresh_profile")
            ],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_ground_forces(self, query, units):
        """نمایش نیروهای زمینی"""
        ground_units = units.get('ground', {})
        
        message = "🪖 **نیروی زمینی**\n\n"
        for unit_name, count in ground_units.items():
            message += f"• {unit_name}: {count:,} نفر\n"
        
        message += f"\n💰 **هزینه ارتقاء:**\n"
        message += "• تازه نفس → سرباز: 100 پول\n"
        message += "• سرباز → حرفه‌ای: 500 پول\n\n"
        message += "برای ارتقاء روی دکمه مورد نظر کلیک کنید."
        
        keyboard = []
        for unit_name in ground_units.keys():
            if "تازه" in unit_name:
                keyboard.append([
                    InlineKeyboardButton(f"⬆️ ارتقاء {unit_name}", callback_data=f"upgrade_{unit_name}")
                ])
        
        keyboard.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_economy_menu(self, query, resources):
        """نمایش منوی اقتصادی"""
        message = (
            f"🏭 **بخش اقتصادی**\n\n"
            f"💰 **موجودی:**\n"
            f"• پول: {resources.get('money', 0):,}\n"
            f"• نفت: {resources.get('oil', 0):,}\n"
            f"• برق: {resources.get('electricity', 0):,}\n\n"
            f"🏢 **سازه‌های اقتصادی:**\n"
            f"• کارخانه: 3 عدد\n"
            f"• معدن: 2 عدد\n"
            f"• نیروگاه: 2 عدد\n\n"
            f"📈 **درآمد ماهانه:**\n"
            f"• از کارخانه‌ها: 5,000 پول\n"
            f"• از معادن: 2,000 نفت\n"
            f"• از نیروگاه: 3,000 برق"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🏭 ساخت کارخانه", callback_data="build_factory"),
                InlineKeyboardButton("⛏ ساخت معدن", callback_data="build_mine")
            ],
            [
                InlineKeyboardButton("⚡ ساخت نیروگاه", callback_data="build_power"),
                InlineKeyboardButton("💵 دریافت وام", callback_data="menu_loan")
            ],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_attack_menu(self, query, attacker_country):
        """نمایش منوی حمله"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # دریافت کشورهای دیگر (بازیکنان)
            cursor.execute(
                """SELECT user_id, country 
                FROM users 
                WHERE bot_id = ? AND user_id != ? AND country != ?""",
                (self.bot_id, query.from_user.id, attacker_country)
            )
            players = cursor.fetchall()
            
            # دریافت کشورهای AI
            cursor.execute(
                "SELECT id, name FROM ai_countries WHERE bot_id = ?",
                (self.bot_id,)
            )
            ai_countries = cursor.fetchall()
        
        keyboard = []
        
        # اضافه کردن بازیکنان
        if players:
            keyboard.append([InlineKeyboardButton("👥 **بازیکنان:**", callback_data="none")])
            for player in players:
                keyboard.append([
                    InlineKeyboardButton(
                        f"⚔️ {player['country']}",
                        callback_data=f"attack_player_{player['user_id']}"
                    )
                ])
        
        # اضافه کردن AI کشورها
        if ai_countries:
            keyboard.append([InlineKeyboardButton("🤖 **کشورهای AI:**", callback_data="none")])
            for ai in ai_countries:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🤖 {ai['name']}",
                        callback_data=f"attack_ai_{ai['id']}"
                    )
                ])
        
        keyboard.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⚔️ **منوی حمله**\n\n"
            f"کشور شما: {attacker_country}\n"
            f"هدف خود را برای حمله انتخاب کنید:\n\n"
            f"⚠️ توجه: حمله ممکن است منجر به تلفات شود.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_guide_menu(self, query):
        """نمایش راهنمای بازی"""
        guide_text = (
            "📘 **راهنمای بازی استراتژیک**\n\n"
            
            "🎯 **هدف بازی:**\n"
            "تبدیل شدن به ابرقدرت جهانی از طریق:\n"
            "• توسعه اقتصادی\n"
            "• تقویت نظامی\n"
            "• تشکیل اتحاد\n"
            "• فتح کشورهای دیگر\n\n"
            
            "⚔️ **سیستم جنگ:**\n"
            "1. نیروهای خود را انتخاب کنید\n"
            "2. کشور هدف را مشخص کنید\n"
            "3. نتیجه بر اساس:\n"
            "   • تعداد و کیفیت نیروها\n"
            "   • سطح تکنولوژی\n"
            "   • روحیه سربازان\n"
            "   • شانس\n\n"
            
            "💰 **اقتصاد:**\n"
            "• پول: برای خرید نیرو و سازه\n"
            "• نفت: برای سوخت نیروها\n"
            "• برق: برای کارخانه‌ها\n"
            "• جمعیت: برای سربازگیری\n\n"
            
            "🏛 **اتحادها:**\n"
            "• با دیگران متحد شوید\n"
            "• از متحدان کمک بگیرید\n"
            "• به متحدان کمک کنید\n\n"
            
            "🤖 **کشورهای AI:**\n"
            "• توسط کامپیوتر کنترل می‌شوند\n"
            "• شخصیت‌های مختلف دارند\n"
            "• ممکن است حمله کنند یا خیانت\n\n"
            
            "💵 **سیستم وام:**\n"
            "• روزی یک بار می‌توانید وام بگیرید\n"
            "• وام باید بازپرداخت شود\n"
            "• عدم بازپرداخت جریمه دارد\n\n"
            
            "🏆 **پایان بازی:**\n"
            "• وقتی یک کشور تمام کشورها را فتح کند\n"
            "• یا پس از ۳۰ روز بازی\n"
            "• کشور برنده جایزه ویژه می‌گیرد"
        )
        
        keyboard = [[InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            guide_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_loan_menu(self, query):
        """نمایش منوی وام"""
        user_id = query.from_user.id
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # بررسی وام‌های قبلی
            cursor.execute(
                """SELECT amount, remaining, created_at 
                FROM loans 
                WHERE user_id = ? AND bot_id = ? 
                ORDER BY created_at DESC LIMIT 1""",
                (user_id, self.bot_id)
            )
            loan_data = cursor.fetchone()
            
            cursor.execute(
                "SELECT resources FROM users WHERE user_id = ? AND bot_id = ?",
                (user_id, self.bot_id)
            )
            user_resources = cursor.fetchone()
        
        if loan_data:
            # کاربر وام دارد
            message = (
                f"💵 **وضعیت وام**\n\n"
                f"📅 تاریخ دریافت: {loan_data['created_at']}\n"
                f"💰 مبلغ وام: {loan_data['amount']:,}\n"
                f"📉 باقی‌مانده: {loan_data['remaining']:,}\n\n"
                f"⏰ می‌توانید پس از ۲۴ ساعت وام جدید بگیرید."
            )
            keyboard = [
                [
                    InlineKeyboardButton("💰 بازپرداخت", callback_data="repay_loan"),
                    InlineKeyboardButton("📋 قوانین", callback_data="loan_rules")
                ],
                [InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_main")]
            ]
        else:
            # کاربر وام ندارد
            resources = json.loads(user_resources['resources']) if user_resources else {}
            message = (
                f"💵 **دریافت وام**\n\n"
                f"💰 موجودی فعلی: {resources.get('money', 0):,}\n\n"
                f"📋 **شرایط وام:**\n"
                f"• حداکثر مبلغ: ۵۰٪ موجودی فعلی\n"
                f"• بازپرداخت: ۲۴ ساعته\n"
                f"• سود: ۱۰٪\n"
                f"• محدودیت: یک بار در روز\n\n"
                f"✅ می‌توانید وام دریافت کنید."
            )
            keyboard = [
                [
                    InlineKeyboardButton("💵 دریافت وام ۵۰۰۰", callback_data="loan_5000"),
                    InlineKeyboardButton("💵 دریافت وام ۱۰۰۰۰", callback_data="loan_10000")
                ],
                [
                    InlineKeyboardButton("📋 قوانین", callback_data="loan_rules"),
                    InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_main")
                ]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def process_loan_request(self, query):
        """پردازش درخواست وام"""
        user_id = query.from_user.id
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # بررسی آخرین وام
            cursor.execute(
                """SELECT created_at 
                FROM loans 
                WHERE user_id = ? AND bot_id = ? 
                ORDER BY created_at DESC LIMIT 1""",
                (user_id, self.bot_id)
            )
            last_loan = cursor.fetchone()
            
            if last_loan:
                last_date = datetime.fromisoformat(last_loan['created_at'])
                now = datetime.now()
                
                if (now - last_date) < timedelta(hours=24):
                    await query.edit_message_text(
                        "❌ **شما امروز وام گرفته‌اید!**\n\n"
                        "می‌توانید ۲۴ ساعت پس از آخرین وام، مجدداً وام دریافت کنید.",
                        parse_mode='Markdown'
                    )
                    return
            
            # دریافت وام ۵۰۰۰
            loan_amount = 5000
            
            # ذخیره وام
            cursor.execute(
                """INSERT INTO loans (user_id, bot_id, amount, remaining) 
                VALUES (?, ?, ?, ?)""",
                (user_id, self.bot_id, loan_amount, loan_amount)
            )
            
            # افزایش پول کاربر
            cursor.execute(
                "SELECT resources FROM users WHERE user_id = ? AND bot_id = ?",
                (user_id, self.bot_id)
            )
            user_data = cursor.fetchone()
            
            if user_data:
                resources = json.loads(user_data['resources'])
                resources['money'] = resources.get('money', 0) + loan_amount
                
                cursor.execute(
                    "UPDATE users SET resources = ? WHERE user_id = ? AND bot_id = ?",
                    (json.dumps(resources), user_id, self.bot_id)
                )
        
        await query.edit_message_text(
            f"✅ **وام دریافت شد!**\n\n"
            f"💰 مبلغ وام: {loan_amount:,}\n"
            f"📅 تاریخ سررسید: فردا این زمان\n"
            f"📉 سود وام: {int(loan_amount * 0.1):,}\n\n"
            f"💡 نکته: سود وام هنگام بازپرداخت کسر می‌شود.",
            parse_mode='Markdown'
        )
    
    async def child_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """راهنمای ربات فرزند"""
        help_text = (
            "🆘 **راهنمای ربات بازی**\n\n"
            
            "🎮 **شروع بازی:**\n"
            "• اگر مالک هستید: /start\n"
            "• اگر کاربر جدید هستید: کشور انتخاب کنید\n"
            "• اگر کاربر قدیمی هستید: /menu\n\n"
            
            "📱 **منوهای اصلی:**\n"
            "• 🪖 نیروی زمینی: مدیریت سربازان\n"
            "• ✈️ نیروی هوایی: مدیریت هواپیماها\n"
            "• 📡 پدافند: سیستم‌های دفاعی\n"
            "• 🚢 نیروی دریایی: کشتی‌های جنگی\n"
            "• 💻 نیروی سایبری: هکرها و تیم‌ها\n"
            "• 💣 تسلیحات ویژه: بمب و موشک\n"
            "• 🏭 اقتصاد: منابع و پول\n"
            "• 🏢 سازه‌ها: ساختمان‌ها\n"
            "• 🧠 تکنولوژی: تحقیقات\n"
            "• ⚔️ حمله: حمله به دیگران\n"
            "• 🏛 اتحاد: همپیمانان\n"
            "• 👤 اطلاعات: پروفایل شما\n"
            "• 📘 راهنما: این صفحه\n"
            "• 🛒 فروشگاه: خرید منابع\n"
            "• ⚙️ تنظیمات: تنظیمات شخصی\n"
            "• 💵 وام: دریافت وام\n\n"
            
            "⚔️ **حمله و دفاع:**\n"
            "• ابتدا نیروهای خود را تقویت کنید\n"
            "• سپس از منوی حمله استفاده کنید\n"
            "• نتیجه بستگی به نیروها و شانس دارد\n\n"
            
            "💰 **اقتصاد و وام:**\n"
            "• روزی یک بار می‌توانید وام بگیرید\n"
            "• منابع خود را در بخش اقتصاد ببینید\n"
            "• سازه‌ها منابع تولید می‌کنند\n\n"
            
            "❓ **مشکلات رایج:**\n"
            "• اگر ربات پاسخ نمی‌دهد: /start\n"
            "• اگر منو نمایش داده نمی‌شود: /menu\n"
            "• اگر مشکل دارید: با مالک تماس بگیرید"
        )
        
        await update.message.reply_text(
            help_text,
            parse_mode='Markdown',
            reply_markup=self.get_main_menu_keyboard(False)
        )
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش پیام‌های متنی"""
        message = update.message.text
        
        if message.startswith("/"):
            await update.message.reply_text(
                "لطفاً از دکمه‌های منو استفاده کنید یا دستور /menu را بزنید."
            )
        else:
            await update.message.reply_text(
                "برای استفاده از ربات، از منوها استفاده کنید.\n"
                "دستور /menu را بزنید یا از /start شروع کنید."
            )

# ==================== سیستم AI ====================

class AISystem:
    def __init__(self, bot_id: int):
        self.bot_id = bot_id
        self.personalities = {
            "aggressive": {"attack_chance": 0.7, "build_chance": 0.3, "ally_chance": 0.1},
            "defensive": {"attack_chance": 0.2, "build_chance": 0.6, "ally_chance": 0.4},
            "unpredictable": {"attack_chance": 0.5, "build_chance": 0.4, "ally_chance": 0.3},
            "neutral": {"attack_chance": 0.3, "build_chance": 0.5, "ally_chance": 0.2},
            "strategic": {"attack_chance": 0.4, "build_chance": 0.6, "ally_chance": 0.5}
        }
    
    async def run_ai_cycle(self):
        """اجرای چرخه تصمیم‌گیری AI"""
        import asyncio
        
        while True:
            await asyncio.sleep(random.randint(600, 1800))  # ۱۰-۳۰ دقیقه
            
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, name, personality, resources FROM ai_countries WHERE bot_id = ?",
                    (self.bot_id,)
                )
                ai_countries = cursor.fetchall()
                
                for ai in ai_countries:
                    await self.make_decision(ai, conn)
    
    async def make_decision(self, ai_country, conn):
        """تصمیم‌گیری برای یک کشور AI"""
        ai_id = ai_country['id']
        personality = ai_country['personality']
        resources = json.loads(ai_country['resources'])
        
        personality_config = self.personalities.get(personality, self.personalities["neutral"])
        
        # تصمیم بر اساس شخصیت
        decision = random.choices(
            ["attack", "build", "ally", "research", "nothing"],
            weights=[
                personality_config["attack_chance"],
                personality_config["build_chance"],
                personality_config["ally_chance"],
                0.1,  # شانس تحقیق
                0.1   # شانس هیچ کاری نکردن
            ]
        )[0]
        
        if decision == "attack":
            await self.ai_attack(ai_id, conn)
        elif decision == "build":
            await self.ai_build(ai_id, resources, conn)
        elif decision == "ally":
            await self.ai_ally(ai_id, conn)
        elif decision == "research":
            await self.ai_research(ai_id, conn)
    
    async def ai_attack(self, ai_id: int, conn):
        """حمله AI به یک کشور"""
        cursor = conn.cursor()
        
        # انتخاب هدف تصادفی (بازیکن یا AI دیگر)
        if random.random() < 0.7:
            # حمله به بازیکن
            cursor.execute(
                "SELECT user_id, country FROM users WHERE bot_id = ? ORDER BY RANDOM() LIMIT 1",
                (self.bot_id,)
            )
            target = cursor.fetchone()
            if target:
                # ثبت حمله در دیتابیس
                cursor.execute(
                    """INSERT INTO battles 
                    (bot_id, attacker_id, defender_id, attacker_type, defender_type, 
                     attacker_country, defender_country, result)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self.bot_id,
                        ai_id,
                        target['user_id'],
                        'ai',
                        'player',
                        f"AI #{ai_id}",
                        target['country'],
                        'pending'
                    )
                )
        else:
            # حمله به AI دیگر
            cursor.execute(
                "SELECT id, name FROM ai_countries WHERE bot_id = ? AND id != ? ORDER BY RANDOM() LIMIT 1",
                (self.bot_id, ai_id)
            )
            target = cursor.fetchone()
            if target:
                cursor.execute(
                    """INSERT INTO battles 
                    (bot_id, attacker_id, defender_id, attacker_type, defender_type,
                     attacker_country, defender_country, result)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self.bot_id,
                        ai_id,
                        target['id'],
                        'ai',
                        'ai',
                        f"AI #{ai_id}",
                        target['name'],
                        'pending'
                    )
                )
    
    async def ai_build(self, ai_id: int, resources: dict, conn):
        """ساخت واحد یا سازه توسط AI"""
        cursor = conn.cursor()
        
        # تصمیم چه چیزی بسازد
        build_options = ["factory", "soldier", "defense", "research"]
        choice = random.choice(build_options)
        
        # به‌روزرسانی منابع
        if choice == "factory" and resources.get('money', 0) > 1000:
            resources['money'] -= 1000
            # افزایش منابع آینده
            pass
        elif choice == "soldier" and resources.get('money', 0) > 500:
            resources['money'] -= 500
            # افزایش نیروها
            pass
        
        cursor.execute(
            "UPDATE ai_countries SET resources = ? WHERE id = ?",
            (json.dumps(resources), ai_id)
        )
    
    async def ai_ally(self, ai_id: int, conn):
        """ایجاد اتحاد توسط AI"""
        cursor = conn.cursor()
        
        # بررسی وجود اتحاد
        cursor.execute(
            "SELECT id FROM alliances WHERE bot_id = ? ORDER BY RANDOM() LIMIT 1",
            (self.bot_id,)
        )
        alliance = cursor.fetchone()
        
        if not alliance:
            # ایجاد اتحاد جدید
            cursor.execute(
                "INSERT INTO alliances (bot_id, name) VALUES (?, ?)",
                (self.bot_id, f"اتحاد AI #{ai_id}")
            )
            alliance_id = cursor.lastrowid
            
            cursor.execute(
                """INSERT INTO alliance_members 
                (alliance_id, ai_id, member_type) 
                VALUES (?, ?, ?)""",
                (alliance_id, ai_id, 'ai')
            )
        else:
            # پیوستن به اتحاد موجود
            cursor.execute(
                """INSERT INTO alliance_members 
                (alliance_id, ai_id, member_type) 
                VALUES (?, ?, ?)""",
                (alliance_id, ai_id, 'ai')
            )
    
    async def ai_research(self, ai_id: int, conn):
        """تحقیقات توسط AI"""
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT technology_level FROM ai_countries WHERE id = ?",
            (ai_id,)
        )
        current_level = cursor.fetchone()
        
        if current_level:
            new_level = current_level['technology_level'] + 1
            cursor.execute(
                "UPDATE ai_countries SET technology_level = ? WHERE id = ?",
                (new_level, ai_id)
            )

# ==================== سیستم جنگ ====================

class BattleSystem:
    @staticmethod
    def calculate_battle_result(attacker_units, defender_units, attacker_tech, defender_tech):
        """محاسبه نتیجه نبرد"""
        import math
        
        # محاسبه قدرت حمله
        attack_power = 0
        for unit, count in attacker_units.items():
            if "حرفه" in unit:
                attack_power += count * 3
            elif "سرباز" in unit:
                attack_power += count * 2
            else:
                attack_power += count
        
        # محاسبه قدرت دفاع
        defense_power = 0
        for unit, count in defender_units.items():
            if "پدافند" in unit:
                defense_power += count * 4
            elif "حرفه" in unit:
                defense_power += count * 3
            else:
                defense_power += count
        
        # ضریب تکنولوژی
        tech_multiplier = 1 + (attacker_tech - defender_tech) * 0.1
        
        # شانس
        luck = random.uniform(0.8, 1.2)
        
        # نتیجه نهایی
        final_attack = attack_power * tech_multiplier * luck
        final_defense = defense_power
        
        if final_attack > final_defense:
            win_margin = (final_attack - final_defense) / final_attack
            return "attacker_wins", win_margin
        else:
            win_margin = (final_defense - final_attack) / final_defense
            return "defender_wins", win_margin

# ==================== اجرای اصلی ====================

async def setup_webhook(app: Application, webhook_url: str):
    """تنظیم وب‌هوک برای Render"""
    await app.bot.set_webhook(f"{webhook_url}/webhook")
    logger.info(f"Webhook set to: {webhook_url}/webhook")

async def health_check():
    """بررسی سلامت برنامه برای Render"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

async def main():
    """تابع اصلی اجرای برنامه"""
    
    # دریافت توکن از متغیرهای محیطی
    MOTHER_TOKEN = os.getenv("MOTHER_BOT_TOKEN")
    
    if not MOTHER_TOKEN:
        logger.error("❌ متغیر محیطی MOTHER_BOT_TOKEN تنظیم نشده!")
        logger.info("لطفاً در Render.com متغیرهای زیر را تنظیم کنید:")
        logger.info("1. MOTHER_BOT_TOKEN: توکن ربات مادر از @BotFather")
        logger.info("2. WEBHOOK_URL: آدرس برنامه شما روی Render")
        return
    
    # ایجاد ربات مادر
    mother_bot = MotherBot(MOTHER_TOKEN)
    
    # تنظیمات وب‌هوک برای Render
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
    PORT = int(os.getenv("PORT", 8443))
    
    if WEBHOOK_URL:
        # حالت تولید: استفاده از وب‌هوک
        await setup_webhook(mother_bot.application, WEBHOOK_URL)
        
        # راه‌اندازی سرور برای دریافت به‌روزرسانی‌ها
        await mother_bot.application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{WEBHOOK_URL}/webhook",
            drop_pending_updates=True
        )
    else:
        # حالت توسعه: استفاده از polling
        logger.info("🚀 شروع ربات مادر در حالت توسعه (polling)...")
        await mother_bot.application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    # ایجاد دایرکتوری برای لاگ‌ها
    os.makedirs("logs", exist_ok=True)
    
    # اجرای برنامه
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 ربات متوقف شد.")
    except Exception as e:
        logger.error(f"❌ خطا در اجرای ربات: {e}")
