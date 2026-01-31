#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import json
import sqlite3
from contextlib import asynccontextmanager

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    PicklePersistence,
)

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== دیتابیس ====================

class Database:
    def __init__(self, db_name="war_game.db"):
        self.db_name = db_name
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_name, check_same_thread=False)
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # جدول ربات‌ها
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS bots (
            bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_token TEXT UNIQUE NOT NULL,
            owner_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        )
        ''')
        
        # جدول کاربران
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            bot_id INTEGER NOT NULL,
            country_name TEXT NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_owner BOOLEAN DEFAULT FALSE,
            resources JSON DEFAULT '{"money": 10000, "oil": 500, "electricity": 1000}',
            units JSON DEFAULT '{}',
            tech_level INTEGER DEFAULT 1,
            morale INTEGER DEFAULT 100,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bot_id) REFERENCES bots (bot_id)
        )
        ''')
        
        # جدول AI کشورها
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_countries (
            ai_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            country_name TEXT NOT NULL,
            personality TEXT DEFAULT 'neutral',
            strategy_state JSON DEFAULT '{}',
            resources JSON DEFAULT '{"money": 15000, "oil": 800, "electricity": 1200}',
            units JSON DEFAULT '{}',
            tech_level INTEGER DEFAULT 1,
            morale INTEGER DEFAULT 100
        )
        ''')
        
        # جدول جنگ‌ها
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS battles (
            battle_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            attacker_id INTEGER,
            defender_id INTEGER,
            attacker_type TEXT CHECK(attacker_type IN ('user', 'ai')),
            defender_type TEXT CHECK(defender_type IN ('user', 'ai')),
            units_used JSON,
            result TEXT,
            loot JSON,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # جدول وام‌ها
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS loans (
            loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            remaining INTEGER NOT NULL,
            last_payment TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        conn.close()

db = Database()

# ==================== ربات مادر (Mother Bot) ====================

class MotherBot:
    def __init__(self, token: str):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
        
    def setup_handlers(self):
        # دستورات ربات مادر
        self.application.add_handler(CommandHandler("start", self.mother_start))
        self.application.add_handler(CommandHandler("addbot", self.add_bot))
        self.application.add_handler(CommandHandler("listbots", self.list_bots))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
    async def mother_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await update.message.reply_text(
            f"👑 سلام {user.first_name}!\n"
            f"به ربات مادر بازی استراتژیک خوش آمدید.\n\n"
            f"🛠 دستورات:\n"
            f"/addbot - افزودن ربات فرزند جدید\n"
            f"/listbots - نمایش ربات‌های شما\n"
            f"/help - راهنما"
        )
    
    async def add_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 برای افزودن ربات فرزند جدید:\n\n"
            "1. به @BotFather مراجعه کنید\n"
            "2. ربات جدید بسازید\n"
            "3. توکن ربات را کپی کنید\n"
            "4. آیدی عددی خود را دریافت کنید (با @userinfobot)\n\n"
            "لطفاً توکن ربات را ارسال کنید:"
        )
        context.user_data['awaiting_token'] = True
    
    async def process_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        token = update.message.text.strip()
        # ذخیره توکن در دیتابیس
        conn = db.get_connection()
        cursor = conn.cursor()
        owner_id = update.effective_user.id
        
        try:
            cursor.execute(
                "INSERT INTO bots (bot_token, owner_id) VALUES (?, ?)",
                (token, owner_id)
            )
            conn.commit()
            bot_id = cursor.lastrowid
            
            await update.message.reply_text(
                f"✅ ربات فرزند با موفقیت اضافه شد!\n"
                f"شناسه ربات: {bot_id}\n\n"
                f"اکنون آیدی عددی خود را ارسال کنید:"
            )
            context.user_data['awaiting_owner_id'] = True
            context.user_data['current_bot_id'] = bot_id
            
        except sqlite3.IntegrityError:
            await update.message.reply_text("❌ این توکن قبلاً ثبت شده است.")
        finally:
            conn.close()
    
    async def list_bots(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT bot_id, created_at, status FROM bots WHERE owner_id = ?",
            (user_id,)
        )
        bots = cursor.fetchall()
        conn.close()
        
        if not bots:
            await update.message.reply_text("🤖 شما هیچ ربات فرزندی ندارید.")
            return
        
        message = "🤖 ربات‌های فرزند شما:\n\n"
        for bot in bots:
            message += f"🔹 شناسه: {bot[0]}\n"
            message += f"   تاریخ ایجاد: {bot[1]}\n"
            message += f"   وضعیت: {bot[2]}\n\n"
        
        await update.message.reply_text(message)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        if data.startswith("bot_"):
            bot_id = int(data.split("_")[1])
            # مدیریت ربات خاص
            pass

# ==================== ربات فرزند (Child Bot) ====================

class ChildBot:
    def __init__(self, token: str, bot_id: int):
        self.token = token
        self.bot_id = bot_id
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
        self.default_units = self.get_default_units()
    
    def get_default_units(self):
        return {
            "ground_forces": {
                "تازه نفس 👶": 10,
                "ارپیجی زن 🚀": 60,
                "تک تیرانداز ⛺": 65,
                "سرباز حرفه ای 🪖": 1185,
                "توپخانه حرفه ای ⚽": 53,
                "سرباز 🙍‍♂️": 100,
                "توپخانه ⚽": 2
            },
            "air_forces": {
                "موشک کوتاه‌برد": 10,
                "موشک میان‌برد": 5,
                "موشک دوربرد": 3,
                "موشک بالستیک": 1,
                "موشک هسته‌ای": 0,
                "جنگنده سبک": 5,
                "جنگنده سنگین": 3,
                "بمب‌افکن": 2,
                "بالگرد رزمی": 4,
                "جت نسل ۴": 2,
                "جت نسل ۵": 1,
                "جت رادارگریز": 0
            },
            "defenses": {
                "پدافند معمولی 📡": 5,
                "پدافند حرفه ای 📡": 312,
                "پدافند قدرتمند 📡": 100
            },
            "navy": {
                "ناو جنگی ⛴️": 20,
                "زیردریایی 💧": 31,
                "کشتی جنگی ⛵️": 105,
                "قایق جنگی 🚤": 10
            },
            "cyber": {
                "هکر حرفه ای 🧑‍💻": 10,
                "تیم هکری 👥": 2
            },
            "bombs": {
                "بمب هسته ای 🍄": 295,
                "بمب کوچولو 💣": 1340
            },
            "factories": {
                "کارخانه ساده 🏚": 3,
                "کارخانه معمولی 🏭": 15,
                "کارخانه خیلی پیشرفته 🏢": 102,
                "کارخانه پستونک سازی 🏢": 226,
                "کارخانه حرفه ای 🏣": 110,
                "معدن 🧑‍🔧": 3,
                "معدن حرفه ای ⚒": 221,
                "معدن پیشرفته ⛏": 10,
                "نیروگاه برق هسته ای ⚡️": 3,
                "نیروگاه پیشرفته ⚡": 110,
                "نیروگاه حرفه ای ⚡": 10,
                "نفت کش 🛢": 10,
                "نفت کش حرفه ای 🛢": 330
            },
            "structures": {
                "بیمارستان 🏥": 3,
                "زایشگاه 🤰": 9,
                "پارک 🏞": 10
            }
        }
    
    def setup_handlers(self):
        # دستورات ربات فرزند
        self.application.add_handler(CommandHandler("start", self.child_start))
        self.application.add_handler(CallbackQueryHandler(self.handle_menu))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def child_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_id = user.id
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # بررسی آیا کاربر وجود دارد
        cursor.execute(
            "SELECT * FROM users WHERE user_id = ? AND bot_id = ?",
            (user_id, self.bot_id)
        )
        user_data = cursor.fetchone()
        
        if not user_data:
            # کاربر جدید
            await self.show_country_selection(update, context)
        else:
            # کاربر موجود
            await self.show_main_menu(update, context, user_data)
        
        conn.close()
    
    async def show_country_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("ایران 🇮🇷", callback_data="country_iran")],
            [InlineKeyboardButton("آمریکا 🇺🇸", callback_data="country_usa")],
            [InlineKeyboardButton("روسیه 🇷🇺", callback_data="country_russia")],
            [InlineKeyboardButton("چین 🇨🇳", callback_data="country_china")],
            [InlineKeyboardButton("آلمان 🇩🇪", callback_data="country_germany")],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🏛 انتخاب کشور\n\n"
            "لطفاً کشور خود را انتخاب کنید:",
            reply_markup=reply_markup
        )
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_data=None):
        if user_data is None:
            user_id = update.effective_user.id
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE user_id = ? AND bot_id = ?",
                (user_id, self.bot_id)
            )
            user_data = cursor.fetchone()
            conn.close()
        
        # بررسی مالک بودن
        is_owner = user_data[6] if user_data else False
        
        if is_owner:
            # پنل مالک
            keyboard = [
                [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
                [InlineKeyboardButton("➕ افزودن کاربر", callback_data="admin_add_user")],
                [InlineKeyboardButton("⚙️ تنظیمات ربات", callback_data="admin_settings")],
                [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "👑 پنل مدیریت\n\n"
                "شما مالک این ربات هستید.",
                reply_markup=reply_markup
            )
        
        # پنل اصلی کاربر
        keyboard = [
            [InlineKeyboardButton("🪖 نیروی زمینی", callback_data="menu_ground")],
            [InlineKeyboardButton("✈️ نیروی هوایی", callback_data="menu_air")],
            [InlineKeyboardButton("📡 پدافندها", callback_data="menu_defense")],
            [InlineKeyboardButton("🚢 نیروی دریایی", callback_data="menu_navy")],
            [InlineKeyboardButton("💻 نیروی سایبری", callback_data="menu_cyber")],
            [InlineKeyboardButton("💣 تسلیحات ویژه", callback_data="menu_special")],
            [InlineKeyboardButton("🏭 بخش اقتصادی", callback_data="menu_economy")],
            [InlineKeyboardButton("🏢 سازه‌ها", callback_data="menu_structures")],
            [InlineKeyboardButton("🧠 تکنولوژی", callback_data="menu_tech")],
            [InlineKeyboardButton("⚔️ حمله", callback_data="menu_attack")],
            [InlineKeyboardButton("🏛 اتحادها", callback_data="menu_alliances")],
            [InlineKeyboardButton("👤 اطلاعات من", callback_data="menu_profile")],
            [InlineKeyboardButton("📘 راهنمای بازی", callback_data="menu_guide")],
            [InlineKeyboardButton("🛒 فروشگاه", callback_data="menu_shop")],
            [InlineKeyboardButton("⚙️ تنظیمات", callback_data="menu_settings")],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        country_name = user_data[2] if user_data else "کشور"
        await update.message.reply_text(
            f"🏰 به {country_name} خوش آمدید!\n\n"
            f"منوی اصلی:",
            reply_markup=reply_markup
        )
    
    async def handle_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("menu_"):
            menu_type = data.split("_")[1]
            
            if menu_type == "ground":
                await self.show_ground_forces(query)
            elif menu_type == "profile":
                await self.show_profile(query)
            elif menu_type == "attack":
                await self.show_attack_menu(query)
            elif menu_type == "shop":
                await self.show_shop(query)
            elif menu_type == "guide":
                await self.show_guide(query)
            # سایر منوها...
    
    async def show_ground_forces(self, query):
        user_id = query.from_user.id
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT units FROM users WHERE user_id = ? AND bot_id = ?",
            (user_id, self.bot_id)
        )
        result = cursor.fetchone()
        conn.close()
        
        units = json.loads(result[0]) if result and result[0] else self.default_units
        
        message = "🪖 نیروی زمینی:\n\n"
        for unit, count in units["ground_forces"].items():
            message += f"{unit}: {count} عدد\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ افزایش نیرو", callback_data="upgrade_ground")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=message,
            reply_markup=reply_markup
        )
    
    async def show_profile(self, query):
        user_id = query.from_user.id
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT country_name, resources, tech_level, morale FROM users WHERE user_id = ? AND bot_id = ?",
            (user_id, self.bot_id)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            country, resources_str, tech, morale = result
            resources = json.loads(resources_str)
            
            message = (
                f"👤 اطلاعات کشور\n\n"
                f"🏛 کشور: {country}\n"
                f"💰 پول: {resources.get('money', 0):,}\n"
                f"🛢 نفت: {resources.get('oil', 0):,}\n"
                f"⚡️ برق: {resources.get('electricity', 0):,}\n"
                f"🧠 سطح تکنولوژی: {tech}\n"
                f"😊 روحیه: {morale}\n\n"
                f"🏆 رتبه: در حال محاسبه..."
            )
        else:
            message = "❌ اطلاعات یافت نشد."
        
        keyboard = [
            [InlineKeyboardButton("💵 دریافت وام", callback_data="loan_request")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=message,
            reply_markup=reply_markup
        )
    
    async def show_attack_menu(self, query):
        # نمایش کشورهای قابل حمله (کاربران و AI)
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # دریافت کشورهای دیگر
        cursor.execute(
            "SELECT user_id, country_name FROM users WHERE bot_id = ? AND user_id != ?",
            (self.bot_id, query.from_user.id)
        )
        other_users = cursor.fetchall()
        
        cursor.execute(
            "SELECT ai_id, country_name FROM ai_countries WHERE bot_id = ?",
            (self.bot_id,)
        )
        ai_countries = cursor.fetchall()
        conn.close()
        
        keyboard = []
        
        # کشورهای کاربران
        for user_id, country in other_users:
            keyboard.append([InlineKeyboardButton(
                f"⚔️ {country} (بازیکن)",
                callback_data=f"attack_user_{user_id}"
            )])
        
        # کشورهای AI
        for ai_id, country in ai_countries:
            keyboard.append([InlineKeyboardButton(
                f"🤖 {country} (AI)",
                callback_data=f"attack_ai_{ai_id}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text="⚔️ انتخاب هدف برای حمله:\n\n"
                 "قرمز: بازیکنان دیگر\n"
                 "آبی: کشورهای AI",
            reply_markup=reply_markup
        )
    
    async def show_shop(self, query):
        keyboard = [
            [InlineKeyboardButton("💰 خرید منابع", callback_data="shop_resources")],
            [InlineKeyboardButton("🪖 خرید نیرو", callback_data="shop_units")],
            [InlineKeyboardButton("🧠 خرید تکنولوژی", callback_data="shop_tech")],
            [InlineKeyboardButton("🏭 خرید کارخانه", callback_data="shop_factory")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text="🛒 فروشگاه\n\n"
                 "موارد قابل خرید:",
            reply_markup=reply_markup
        )
    
    async def show_guide(self, query):
        guide_text = (
            "📘 راهنمای بازی استراتژیک\n\n"
            "🎯 هدف بازی:\n"
            "• تسخیر تمام کشورها و تبدیل شدن به ابرقدرت\n\n"
            "⚔️ مکانیزم حمله:\n"
            "1. نیروهای خود را انتخاب کنید\n"
            "2. کشور هدف را انتخاب کنید\n"
            "3. نتیجه بر اساس نیروها و شانس تعیین می‌شود\n\n"
            "💰 اقتصاد:\n"
            "• منابع: پول، نفت، برق\n"
            "• کارخانه‌ها منابع تولید می‌کنند\n"
            "• می‌توانید روزی یک بار وام دریافت کنید\n\n"
            "🏛 اتحادها:\n"
            "• با دیگران متحد شوید\n"
            "• از متحدان درخواست کمک کنید\n\n"
            "🤖 AI:\n"
            "• برخی کشورها توسط AI کنترل می‌شوند\n"
            "• AI ممکن است حمله کند یا خیانت کند\n\n"
            "💡 نکات:\n"
            "• روحیه نیروها مهم است\n"
            "• تکنولوژی قدرت را افزایش می‌دهد\n"
            "• اقتصاد قرمز منجر به سقوط می‌شود"
        )
        
        keyboard = [[InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=guide_text,
            reply_markup=reply_markup
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # پردازش پیام‌های متنی
        if 'awaiting_token' in context.user_data and context.user_data['awaiting_token']:
            await self.process_token(update, context)
        elif 'awaiting_country_name' in context.user_data and context.user_data['awaiting_country_name']:
            await self.process_country_name(update, context)
        else:
            await update.message.reply_text("لطفاً از منو استفاده کنید.")

# ==================== سیستم AI ====================

class AISystem:
    def __init__(self, bot_id: int):
        self.bot_id = bot_id
    
    async def make_decision(self):
        """هر ۱۰-۳۰ دقیقه یک تصمیم می‌گیرد"""
        import random
        import asyncio
        
        while True:
            # زمان تصادفی بین ۱۰ تا ۳۰ دقیقه
            wait_time = random.randint(600, 1800)
            await asyncio.sleep(wait_time)
            
            conn = db.get_connection()
            cursor = conn.cursor()
            
            # دریافت تمام AI کشورها
            cursor.execute(
                "SELECT ai_id, personality, strategy_state FROM ai_countries WHERE bot_id = ?",
                (self.bot_id,)
            )
            ai_countries = cursor.fetchall()
            
            for ai in ai_countries:
                ai_id, personality, strategy_state_str = ai
                strategy_state = json.loads(strategy_state_str) if strategy_state_str else {}
                
                # تصمیم‌گیری بر اساس شخصیت
                decision = self.generate_decision(personality, strategy_state)
                
                # اجرای تصمیم
                await self.execute_decision(ai_id, decision)
            
            conn.close()
    
    def generate_decision(self, personality: str, state: dict):
        import random
        
        decisions = []
        
        if personality == "aggressive":
            # احتمال حمله بالا
            if random.random() < 0.7:
                decisions.append(("attack", None))
            if random.random() < 0.3:
                decisions.append(("build", "military"))
        
        elif personality == "defensive":
            # تمرکز بر دفاع و اقتصاد
            if random.random() < 0.8:
                decisions.append(("build", "defense"))
            if random.random() < 0.6:
                decisions.append(("build", "economy"))
        
        elif personality == "unpredictable":
            # تصمیمات غیرقابل پیش‌بینی
            options = ["attack", "ally", "betray", "build", "research"]
            decision = random.choice(options)
            if decision == "build":
                build_type = random.choice(["military", "economy", "defense", "tech"])
                decisions.append((decision, build_type))
            else:
                decisions.append((decision, None))
        
        return decisions
    
    async def execute_decision(self, ai_id: int, decisions: list):
        conn = db.get_connection()
        cursor = conn.cursor()
        
        for decision, subtype in decisions:
            if decision == "attack":
                # انتخاب هدف تصادفی
                cursor.execute(
                    "SELECT user_id FROM users WHERE bot_id = ? ORDER BY RANDOM() LIMIT 1",
                    (self.bot_id,)
                )
                target = cursor.fetchone()
                if target:
                    # حمله به هدف
                    pass
            
            elif decision == "build":
                # ساخت واحد یا سازه
                pass
        
        conn.close()

# ==================== سیستم وام ====================

class LoanSystem:
    @staticmethod
    def can_get_loan(user_id: int) -> bool:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # بررسی آخرین وام
        cursor.execute(
            "SELECT created_at FROM loans WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        last_loan = cursor.fetchone()
        conn.close()
        
        if not last_loan:
            return True
        
        from datetime import datetime, timedelta
        last_date = datetime.fromisoformat(last_loan[0])
        now = datetime.now()
        
        # حداقل ۲۴ ساعت بین وام‌ها
        return (now - last_date) >= timedelta(hours=24)
    
    @staticmethod
    def give_loan(user_id: int, amount: int = 5000):
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # افزودن وام
        cursor.execute(
            "INSERT INTO loans (user_id, amount, remaining) VALUES (?, ?, ?)",
            (user_id, amount, amount)
        )
        
        # افزایش پول کاربر
        cursor.execute(
            "SELECT resources FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        if result:
            resources = json.loads(result[0])
            resources['money'] = resources.get('money', 0) + amount
            
            cursor.execute(
                "UPDATE users SET resources = ? WHERE user_id = ?",
                (json.dumps(resources), user_id)
            )
        
        conn.commit()
        conn.close()

# ==================== سیستم جنگ ====================

class BattleSystem:
    @staticmethod
    async def simulate_battle(attacker_id: int, defender_id: int, 
                            attacker_type: str, defender_type: str,
                            units_used: dict, bot_id: int):
        """
        شبیه‌سازی نبرد با محاسبات پیشرفته
        """
        import random
        import math
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # دریافت اطلاعات حمله‌کننده
        if attacker_type == "user":
            cursor.execute(
                "SELECT units, tech_level FROM users WHERE user_id = ? AND bot_id = ?",
                (attacker_id, bot_id)
            )
        else:
            cursor.execute(
                "SELECT units, tech_level FROM ai_countries WHERE ai_id = ?",
                (attacker_id,)
            )
        attacker_data = cursor.fetchone()
        
        # دریافت اطلاعات مدافع
        if defender_type == "user":
            cursor.execute(
                "SELECT units, tech_level, morale FROM users WHERE user_id = ? AND bot_id = ?",
                (defender_id, bot_id)
            )
        else:
            cursor.execute(
                "SELECT units, tech_level, morale FROM ai_countries WHERE ai_id = ?",
                (defender_id,)
            )
        defender_data = cursor.fetchone()
        
        if not attacker_data or not defender_data:
            return None
        
        # محاسبات نبرد
        attacker_units = json.loads(attacker_data[0])
        defender_units = json.loads(defender_data[0])
        
        # قدرت حمله‌کننده
        attack_power = 0
        for unit_type, units in units_used.items():
            if unit_type in attacker_units:
                attack_power += units * random.uniform(0.8, 1.2)
        
        # قدرت دفاع مدافع
        defense_power = 0
        for unit_type, count in defender_units.get("defenses", {}).items():
            defense_power += count * random.uniform(0.7, 1.1)
        
        # ضریب تکنولوژی
        tech_bonus = 1 + (attacker_data[1] - defender_data[1]) * 0.1
        
        # ضریب روحیه
        morale_bonus = 1 + (defender_data[2] - 50) * 0.01
        
        # محاسبه نهایی
        total_attack = attack_power * tech_bonus
        total_defense = defense_power * morale_bonus
        
        # شانس
        luck = random.uniform(0.8, 1.2)
        
        # نتیجه
        if total_attack * luck > total_defense:
            result = "attacker_wins"
            loot_multiplier = min(0.3, (total_attack - total_defense) / total_attack * 0.5)
        else:
            result = "defender_wins"
            loot_multiplier = 0
        
        # ثبت نبرد
        battle_data = {
            "attacker_power": total_attack,
            "defender_power": total_defense,
            "luck_factor": luck,
            "result": result
        }
        
        cursor.execute(
            """INSERT INTO battles 
            (bot_id, attacker_id, defender_id, attacker_type, defender_type, units_used, result, loot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (bot_id, attacker_id, defender_id, attacker_type, defender_type,
             json.dumps(units_used), result, json.dumps({"multiplier": loot_multiplier}))
        )
        
        conn.commit()
        conn.close()
        
        return battle_data

# ==================== فایل اصلی اجرا ====================

async def main():
    # توکن ربات مادر (از متغیر محیطی)
    MOTHER_TOKEN = os.getenv("MOTHER_BOT_TOKEN")
    
    if not MOTHER_TOKEN:
        logger.error("مقدار MOTHER_BOT_TOKEN تنظیم نشده!")
        return
    
    # ایجاد ربات مادر
    mother_bot = MotherBot(MOTHER_TOKEN)
    
    # راه‌اندازی وب‌هوک برای Render
    PORT = int(os.environ.get("PORT", 8443))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "") + "/webhook"
    
    if WEBHOOK_URL:
        await mother_bot.application.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook set to {WEBHOOK_URL}")
        
        # اجرا با وب‌هوک
        await mother_bot.application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL
        )
    else:
        # اجرا با polling (برای تست)
        logger.info("Starting with polling...")
        await mother_bot.application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())