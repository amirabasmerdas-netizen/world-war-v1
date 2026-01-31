#!/usr/bin/env python3
import os
import sys
import sqlite3
import json

def setup_database():
    """تنظیم اولیه دیتابیس"""
    conn = sqlite3.connect("war_game.db")
    cursor = conn.cursor()
    
    # ایجاد جداول
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bots (
        bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_token TEXT UNIQUE NOT NULL,
        owner_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active'
    )
    ''')
    
    # ایجاد سایر جداول...
    
    conn.commit()
    conn.close()
    
    print("✅ دیتابیس تنظیم شد.")

def create_sample_ai():
    """ایجاد کشورهای AI نمونه"""
    conn = sqlite3.connect("war_game.db")
    cursor = conn.cursor()
    
    ai_countries = [
        ("آمریکا 🤖", "aggressive"),
        ("روسیه 🤖", "unpredictable"),
        ("چین 🤖", "defensive"),
        ("آلمان 🤖", "neutral"),
    ]
    
    for country, personality in ai_countries:
        cursor.execute('''
        INSERT INTO ai_countries (bot_id, country_name, personality, resources)
        VALUES (?, ?, ?, ?)
        ''', (1, country, personality, json.dumps({"money": 20000, "oil": 1000, "electricity": 1500})))
    
    conn.commit()
    conn.close()
    
    print("✅ کشورهای AI ایجاد شدند.")

if __name__ == "__main__":
    setup_database()
    create_sample_ai()
    
    print("\n🎮 تنظیمات اولیه کامل شد!")
    print("برای شروع، فایل main.py را اجرا کنید.")