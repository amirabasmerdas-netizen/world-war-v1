#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
import asyncio
import json
import sqlite3
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from contextlib import contextmanager

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    PicklePersistence,
)

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# حالت‌های مکالمه
WAITING_TOKEN, WAITING_OWNER_ID = range(2)

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
            
            conn.commit()
    
    @contextmanager
    def get_connection(self):
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

db = DatabaseManager()

# ==================== مدیریت ربات‌ها ====================

class BotManager:
    _bots = {}
    
    @classmethod
    def get_bot(cls, bot_id: int):
        """دریافت ربات با شناسه"""
        return cls._bots.get(bot_id)
    
    @classmethod
    def add_bot(cls, bot_id: int, token: str):
        """افزودن ربات جدید"""
        if bot_id not in cls._bots:
            cls._bots[bot_id] = ChildBot(token, bot_id)
            logger.info(f"ربات فرزند {bot_id} اضافه شد")
        return cls._bots[bot_id]
    
    @classmethod
    def remove_bot(cls, bot_id: int):
        """حذف ربات"""
        if bot_id in cls._bots:
            del cls._bots[bot_id]
            logger.info(f"ربات فرزند {bot_id} حذف شد")
    
    @classmethod
    async def start_all_bots(cls):
        """راه‌اندازی تمام ربات‌ها"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, token FROM bots WHERE status = 'active'")
            bots = cursor.fetchall()
            
            for bot in bots:
                try:
                    cls.add_bot(bot['id'], bot['token'])
                    logger.info(f"ربات {bot['id']} راه‌اندازی شد")
                except Exception as e:
                    logger.error(f"خطا در راه‌اندازی ربات {bot['id']}: {e}")

# ==================== ربات مادر ====================

async def mother_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ربات مادر"""
    user = update.effective_user
    await update.message.reply_text(
        f"👑 سلام {user.first_name}!\n"
        f"به ربات مادر بازی استراتژیک خوش آمدید.\n\n"
        f"📋 دستورات اصلی:\n"
        f"/addbot - ایجاد ربات فرزند جدید\n"
        f"/listbots - مشاهده ربات‌های شما\n"
        f"/help - راهنمای کامل"
    )

async def start_add_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def process_bot_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def process_owner_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    user = update.effective_user
    
    if not token:
        await update.message.reply_text("❌ توکن یافت نشد! لطفاً دوباره شروع کنید: /addbot")
        return ConversationHandler.END
    
    # ذخیره در دیتابیس
    with db.get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO bots (token, owner_id) VALUES (?, ?)",
                (token, owner_id)
            )
            bot_id = cursor.lastrowid
            
            # افزودن به مدیریت ربات‌ها
            BotManager.add_bot(bot_id, token)
            
            await update.message.reply_text(
                f"🎉 **ربات فرزند با موفقیت ایجاد شد!**\n\n"
                f"🔑 شناسه ربات: `{bot_id}`\n"
                f"👤 مالک: آیدی {owner_id}\n\n"
                f"✅ اکنون می‌توانید به ربات فرزند مراجعه کنید و شروع به بازی کنید!\n\n"
                f"🤖 ربات: https://t.me/{update.message.text.split(':')[0]}",
                parse_mode='Markdown'
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
        except Exception as e:
            logger.error(f"خطا در ثبت ربات: {e}")
            await update.message.reply_text(
                f"❌ خطا در ثبت ربات: {str(e)}"
            )
            return ConversationHandler.END

async def cancel_add_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو فرآیند افزودن ربات"""
    if 'bot_token' in context.user_data:
        del context.user_data['bot_token']
    
    await update.message.reply_text("❌ فرآیند ایجاد ربات لغو شد.")
    return ConversationHandler.END

async def list_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست ربات‌های کاربر"""
    user_id = update.effective_user.id
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, created_at, status FROM bots WHERE owner_id = ?",
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
            f"   📅 ایجاد: {bot['created_at'][:10]}\n"
            f"   🟢 وضعیت: {bot['status']}\n\n"
        )
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def mother_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "A: عددی منحصربه‌فرد شما در تلگرام\n\n"
        "Q: هر کاربر چند ربات می‌تواند داشته باشد؟\n"
        "A: محدودیتی وجود ندارد"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ==================== کلاس ربات فرزند ====================

class ChildBot:
    def __init__(self, token: str, bot_id: int):
        self.token = token
        self.bot_id = bot_id
        self.application = None
        self.setup_application()
        
    def setup_application(self):
        """تنظیم اپلیکیشن ربات فرزند"""
        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """تنظیم هندلرهای ربات فرزند"""
        # هندلرهای اصلی
        self.application.add_handler(CommandHandler("start", self.child_start))
        self.application.add_handler(CommandHandler("help", self.child_help))
        self.application.add_handler(CommandHandler("menu", self.show_main_menu))
        
        # هندلر برای کلیک روی دکمه‌ها
        self.application.add_handler(CallbackQueryHandler(self.handle_child_callback))
        
        # هندلر برای پیام‌های متنی
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message)
        )
    
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
                "جنگنده سبک": 2
            },
            "defense": {
                "پدافند معمولی 📡": 5,
                "پدافند حرفه ای 📡": 10
            },
            "navy": {
                "ناو جنگی ⛴️": 2,
                "کشتی جنگی ⛵️": 5
            }
        }
    
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
                InlineKeyboardButton("🎮 شروع بازی", callback_data="start_game")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "👑 **پنل مدیریت ربات**\n\n"
            "شما مالک این ربات هستید.\n"
            "برای شروع بازی روی دکمه زیر کلیک کنید.",
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
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🏛 **انتخاب کشور**\n\n"
            "لطفاً کشور خود را انتخاب کنید:",
            reply_markup=reply_markup
        )
    
    def get_main_menu_keyboard(self, is_owner: bool = False):
        """ایجاد کیبورد منوی اصلی"""
        keyboard = []
        
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
                InlineKeyboardButton("🏭 اقتصاد", callback_data="menu_economy"),
                InlineKeyboardButton("🏢 سازه‌ها", callback_data="menu_structures")
            ],
            [
                InlineKeyboardButton("⚔️ حمله", callback_data="menu_attack"),
                InlineKeyboardButton("👤 اطلاعات", callback_data="menu_profile")
            ],
            [
                InlineKeyboardButton("📘 راهنما", callback_data="menu_guide"),
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
                "منوی اصلی بازی:",
                reply_markup=self.get_main_menu_keyboard(is_owner),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "لطفاً ابتدا با دستور /start شروع کنید."
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
            await self.show_menu(query, menu_type, user_id)
        
        elif data == "back_main":
            await self.show_main_menu_callback(query, user_id)
    
    async def start_new_game(self, query):
        """شروع بازی جدید"""
        user_id = query.from_user.id
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # حذف کاربر قبلی اگر وجود دارد
            cursor.execute(
                "DELETE FROM users WHERE user_id = ? AND bot_id = ?",
                (user_id, self.bot_id)
            )
            
            # ایجاد کاربر جدید به عنوان مالک
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
                    "ایران 🇮🇷",
                    query.from_user.username,
                    query.from_user.first_name,
                    query.from_user.last_name,
                    True,
                    json.dumps(default_resources),
                    json.dumps(self.get_default_units())
                )
            )
            
            # ایجاد کشورهای AI
            await self.create_default_ai_countries(conn)
        
        keyboard = [[InlineKeyboardButton("🏰 منوی اصلی", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎮 **بازی جدید شروع شد!**\n\n"
            "کشور شما با منابع اولیه ایجاد شد.\n"
            "کشورهای AI نیز آماده هستند.\n\n"
            "از منوی اصلی برای شروع استفاده کنید.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def create_default_ai_countries(self, conn):
        """ایجاد کشورهای AI پیش‌فرض"""
        cursor = conn.cursor()
        
        ai_countries = [
            ("آمریکا 🤖", "aggressive", {"money": 15000, "oil": 800, "electricity": 1200, "population": 1500}),
            ("روسیه 🤖", "unpredictable", {"money": 14000, "oil": 900, "electricity": 1100, "population": 1400}),
        ]
        
        for name, personality, resources in ai_countries:
            cursor.execute(
                """INSERT INTO ai_countries 
                (bot_id, name, personality, resources) 
                VALUES (?, ?, ?, ?)""",
                (self.bot_id, name, personality, json.dumps(resources))
            )
    
    async def assign_country(self, query, user_id: int, country_code: str):
        """اختصاص کشور به کاربر"""
        country_map = {
            "iran": "ایران 🇮🇷",
            "iraq": "عراق 🇮🇶",
            "turkey": "ترکیه 🇹🇷",
            "saudi": "عربستان 🇸🇦"
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
            f"به بازی استراتژیک خوش آمدید!\n",
            reply_markup=self.get_main_menu_keyboard(False),
            parse_mode='Markdown'
        )
    
    async def show_menu(self, query, menu_type: str, user_id: int):
        """نمایش منوهای مختلف"""
        
        if menu_type == "profile":
            await self.show_profile_menu(query, user_id)
        
        elif menu_type == "ground":
            await self.show_ground_forces(query, user_id)
        
        elif menu_type == "economy":
            await self.show_economy_menu(query, user_id)
        
        elif menu_type == "guide":
            await self.show_guide_menu(query)
        
        elif menu_type == "loan":
            await self.show_loan_menu(query, user_id)
    
    async def show_profile_menu(self, query, user_id: int):
        """نمایش پروفایل کاربر"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT country, resources, units FROM users WHERE user_id = ? AND bot_id = ?",
                (user_id, self.bot_id)
            )
            user_data = cursor.fetchone()
        
        if not user_data:
            await query.edit_message_text("❌ کاربر یافت نشد!")
            return
        
        country = user_data['country']
        resources = json.loads(user_data['resources'])
        units = json.loads(user_data['units'])
        
        total_troops = 0
        for category in units.values():
            if isinstance(category, dict):
                total_troops += sum(category.values())
        
        message = (
            f"👤 **پروفایل کشور {country}**\n\n"
            f"💰 **منابع:**\n"
            f"  • پول: {resources.get('money', 0):,}\n"
            f"  • نفت: {resources.get('oil', 0):,}\n"
            f"  • برق: {resources.get('electricity', 0):,}\n"
            f"  • جمعیت: {resources.get('population', 0):,}\n\n"
            f"🎖 **نیروها:**\n"
            f"  • کل نیروها: {total_troops:,}\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 به‌روزرسانی", callback_data="menu_profile")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_ground_forces(self, query, user_id: int):
        """نمایش نیروهای زمینی"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT units FROM users WHERE user_id = ? AND bot_id = ?",
                (user_id, self.bot_id)
            )
            user_data = cursor.fetchone()
        
        if not user_data:
            await query.edit_message_text("❌ کاربر یافت نشد!")
            return
        
        units = json.loads(user_data['units'])
        ground_units = units.get('ground', {})
        
        message = "🪖 **نیروی زمینی**\n\n"
        for unit_name, count in ground_units.items():
            message += f"• {unit_name}: {count:,} نفر\n"
        
        message += f"\n💰 **هزینه ارتقاء:**\n"
        message += "• تازه نفس → سرباز: 100 پول\n"
        
        keyboard = [
            [InlineKeyboardButton("⬆️ ارتقاء نیروها", callback_data="upgrade_ground")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_economy_menu(self, query, user_id: int):
        """نمایش منوی اقتصادی"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT resources FROM users WHERE user_id = ? AND bot_id = ?",
                (user_id, self.bot_id)
            )
            user_data = cursor.fetchone()
        
        if not user_data:
            await query.edit_message_text("❌ کاربر یافت نشد!")
            return
        
        resources = json.loads(user_data['resources'])
        
        message = (
            f"🏭 **بخش اقتصادی**\n\n"
            f"💰 **موجودی:**\n"
            f"• پول: {resources.get('money', 0):,}\n"
            f"• نفت: {resources.get('oil', 0):,}\n"
            f"• برق: {resources.get('electricity', 0):,}\n\n"
            f"📈 **درآمد ماهانه:**\n"
            f"• از کارخانه‌ها: 2,000 پول\n"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🏭 ساخت کارخانه", callback_data="build_factory"),
                InlineKeyboardButton("💵 دریافت وام", callback_data="menu_loan")
            ],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_guide_menu(self, query):
        """نمایش راهنمای بازی"""
        guide_text = (
            "📘 **راهنمای بازی استراتژیک**\n\n"
            
            "🎯 **هدف بازی:**\n"
            "تبدیل شدن به ابرقدرت جهانی\n\n"
            
            "⚔️ **سیستم جنگ:**\n"
            "• نیروهای خود را تقویت کنید\n"
            "• به کشورهای دیگر حمله کنید\n"
            "• نتیجه بستگی به نیروها و شانس دارد\n\n"
            
            "💰 **اقتصاد:**\n"
            "• پول: برای خرید نیرو و سازه\n"
            "• نفت: برای سوخت نیروها\n"
            "• برق: برای کارخانه‌ها\n\n"
            
            "💵 **سیستم وام:**\n"
            "• روزی یک بار می‌توانید وام بگیرید\n"
            "• وام باید بازپرداخت شود\n"
        )
        
        keyboard = [[InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            guide_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_loan_menu(self, query, user_id: int):
        """نمایش منوی وام"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # بررسی وام‌های قبلی
            cursor.execute(
                """SELECT created_at 
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
                f"📅 تاریخ دریافت: {loan_data['created_at'][:10]}\n\n"
                f"⏰ می‌توانید پس از ۲۴ ساعت وام جدید بگیرید."
            )
            keyboard = [
                [InlineKeyboardButton("📋 قوانین", callback_data="loan_rules")],
                [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]
            ]
        else:
            # کاربر وام ندارد
            resources = json.loads(user_resources['resources']) if user_resources else {}
            message = (
                f"💵 **دریافت وام**\n\n"
                f"💰 موجودی فعلی: {resources.get('money', 0):,}\n\n"
                f"📋 **شرایط وام:**\n"
                f"• حداکثر مبلغ: ۵٬۰۰۰\n"
                f"• بازپرداخت: ۲۴ ساعته\n"
                f"• سود: ۱۰٪\n"
                f"• محدودیت: یک بار در روز\n\n"
                f"✅ می‌توانید وام دریافت کنید."
            )
            keyboard = [
                [
                    InlineKeyboardButton("💵 وام ۵۰۰۰", callback_data="loan_5000"),
                    InlineKeyboardButton("📋 قوانین", callback_data="loan_rules")
                ],
                [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_main_menu_callback(self, query, user_id: int):
        """نمایش منوی اصلی از طریق callback"""
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
            
            await query.edit_message_text(
                f"🏰 **کشور {country}**\n\n"
                "منوی اصلی بازی:",
                reply_markup=self.get_main_menu_keyboard(is_owner),
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "لطفاً ابتدا با دستور /start شروع کنید."
            )
    
    async def child_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """راهنمای ربات فرزند"""
        help_text = (
            "🆘 **راهنمای ربات بازی**\n\n"
            
            "🎮 **شروع بازی:**\n"
            "• مالک: /start و شروع بازی\n"
            "• کاربر جدید: کشور انتخاب کنید\n"
            "• کاربر قدیمی: /menu\n\n"
            
            "📱 **منوهای اصلی:**\n"
            "• 🪖 نیروی زمینی: مدیریت سربازان\n"
            "• ✈️ نیروی هوایی: مدیریت هواپیماها\n"
            "• 📡 پدافند: سیستم‌های دفاعی\n"
            "• 🚢 نیروی دریایی: کشتی‌های جنگی\n"
            "• 🏭 اقتصاد: منابع و پول\n"
            "• 🏢 سازه‌ها: ساختمان‌ها\n"
            "• ⚔️ حمله: حمله به دیگران\n"
            "• 👤 اطلاعات: پروفایل شما\n"
            "• 📘 راهنما: این صفحه\n"
            "• 💵 وام: دریافت وام\n\n"
            
            "❓ **مشکلات رایج:**\n"
            "• اگر ربات پاسخ نمی‌دهد: /start\n"
            "• اگر منو نمایش داده نمی‌شود: /menu"
        )
        
        await update.message.reply_text(
            help_text,
            parse_mode='Markdown'
        )
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش پیام‌های متنی"""
        await update.message.reply_text(
            "برای استفاده از ربات، از منوها استفاده کنید.\n"
            "دستور /menu را بزنید یا از /start شروع کنید."
        )
    
    async def start_polling(self):
        """شروع polling برای ربات فرزند"""
        if self.application:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            logger.info(f"ربات فرزند {self.bot_id} شروع به کار کرد")
    
    async def stop_polling(self):
        """توقف polling برای ربات فرزند"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info(f"ربات فرزند {self.bot_id} متوقف شد")

# ==================== اجرای اصلی ====================

async def setup_webhook(app: Application, webhook_url: str, port: int = 8443):
    """تنظیم وب‌هوک برای Render"""
    await app.bot.set_webhook(f"{webhook_url}/webhook")
    logger.info(f"Webhook set to: {webhook_url}/webhook")
    
    # ایجاد سرور برای دریافت به‌روزرسانی‌ها
    from aiohttp import web
    
    async def handle_webhook(request):
        """مدیریت درخواست‌های وب‌هوک"""
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        return web.Response(text="OK")
    
    # راه‌اندازی سرور
    server = web.Application()
    server.router.add_post('/webhook', handle_webhook)
    
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    return runner

async def main():
    """تابع اصلی اجرای برنامه"""
    
    # دریافت توکن از متغیرهای محیطی
    MOTHER_TOKEN = os.getenv("MOTHER_BOT_TOKEN")
    
    if not MOTHER_TOKEN:
        logger.error("❌ متغیر محیطی MOTHER_BOT_TOKEN تنظیم نشده!")
        logger.info("لطفاً توکن ربات مادر را تنظیم کنید.")
        return
    
    # ایجاد اپلیکیشن ربات مادر
    mother_app = Application.builder().token(MOTHER_TOKEN).build()
    
    # تنظیم هندلرهای ربات مادر
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('addbot', start_add_bot)],
        states={
            WAITING_TOKEN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_bot_token)
            ],
            WAITING_OWNER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_owner_id)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_add_bot)]
    )
    
    mother_app.add_handler(conv_handler)
    mother_app.add_handler(CommandHandler('start', mother_start))
    mother_app.add_handler(CommandHandler('listbots', list_bots))
    mother_app.add_handler(CommandHandler('help', mother_help))
    
    # راه‌اندازی ربات‌های فرزند موجود
    await BotManager.start_all_bots()
    
    # تنظیمات وب‌هوک برای Render
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
    PORT = int(os.getenv("PORT", 8443))
    
    if WEBHOOK_URL:
        # حالت تولید: استفاده از وب‌هوک
        logger.info(f"🚀 شروع ربات مادر با وب‌هوک روی پورت {PORT}...")
        await setup_webhook(mother_app, WEBHOOK_URL, PORT)
        
        # اجرای ربات‌های فرزند
        for bot in BotManager._bots.values():
            try:
                await bot.start_polling()
            except Exception as e:
                logger.error(f"خطا در راه‌اندازی ربات فرزند: {e}")
        
        # نگه داشتن برنامه در حال اجرا
        await asyncio.Event().wait()
        
    else:
        # حالت توسعه: استفاده از polling
        logger.info("🚀 شروع ربات مادر در حالت توسعه (polling)...")
        
        # اجرای ربات مادر
        await mother_app.initialize()
        await mother_app.start()
        await mother_app.updater.start_polling()
        
        # اجرای ربات‌های فرزند
        for bot in BotManager._bots.values():
            try:
                await bot.start_polling()
            except Exception as e:
                logger.error(f"خطا در راه‌اندازی ربات فرزند: {e}")
        
        # نگه داشتن برنامه در حال اجرا
        await asyncio.Event().wait()

async def shutdown():
    """خاموش کردن برنامه"""
    logger.info("👋 در حال خاموش کردن ربات‌ها...")
    
    # توقف تمام ربات‌های فرزند
    for bot in BotManager._bots.values():
        try:
            await bot.stop_polling()
        except Exception as e:
            logger.error(f"خطا در توقف ربات فرزند: {e}")
    
    logger.info("✅ ربات‌ها با موفقیت متوقف شدند.")

if __name__ == "__main__":
    try:
        # ایجاد دایرکتوری‌های لازم
        os.makedirs("data", exist_ok=True)
        
        # اجرای برنامه
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("دریافت سیگنال توقف...")
        asyncio.run(shutdown())
    except Exception as e:
        logger.error(f"❌ خطا در اجرای ربات: {e}")
        import traceback
        logger.error(traceback.format_exc())
