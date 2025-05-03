#!/usr/bin/env python

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    ApplicationBuilder,  # New in v20+
)
import random
import os
import sqlite3
import json
from datetime import datetime


os.environ["SSL_CERT_FILE"] = "./cacert-2025-02-25.pem" # hack to fix SSL error. Shouldn't need this in production.

TOKEN = ""

# ------ Bot Functions ------
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🎉 Welcome to Quiz Bot!\n"
        "Use /quiz <category> to start (e.g., /quiz science).\n"
        "Categories: science, geography, math\n"
        "View scores with /leaderboard"
    )

def fetch_questions(category=None):
    conn = sqlite3.connect('quiz_bot.db')
    cursor = conn.cursor()
    if category:
        cursor.execute('SELECT question, options, correct_answer FROM questions WHERE category=?', (category,))
    else:
        cursor.execute('SELECT question, options, correct_answer FROM questions')
    questions = cursor.fetchall()
    conn.close()
    return questions

def update_score(user_id, chat_id, points, update: Update = None):
    conn = sqlite3.connect('quiz_bot.db')
    cursor = conn.cursor()
    
    # Update user info if Update object is provided
    if update:
        user = update.effective_user
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_updated = CURRENT_TIMESTAMP
        ''', (user.id, user.username, user.first_name, user.last_name))
    
    # Update score
    cursor.execute('''
        INSERT INTO scores (user_id, chat_id, score)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, chat_id) DO UPDATE SET score = score + ?
    ''', (user_id, chat_id, points, points))
    
    conn.commit()
    conn.close()


async def quiz(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text(
            "⚠️ Please specify a category!\n"
            "Available categories: science, geography, math\n"
            "Example: /quiz science"
        )
        return

    category = context.args[0].lower()
    valid_categories = ['science', 'geography', 'math']
    
    if category not in valid_categories:
        await update.message.reply_text(
            f"⚠️ Invalid category! Choose from: {', '.join(valid_categories)}"
        )
        return

    try:
        questions = fetch_questions(category)
        if not questions:
            await update.message.reply_text("⚠️ No questions found for this category!")
            return

        question, options_json, correct_answer = random.choice(questions)
        options = json.loads(options_json)

        keyboard = [
            [InlineKeyboardButton(opt, callback_data=f"ans_{i}_{correct_answer}")]
            for i, opt in enumerate(options)
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = await update.message.reply_text(
            f"📚 {category.capitalize()} Quiz:\n\n{question}\n\n⏳ You have 15 seconds!",
            reply_markup=reply_markup
        )

        context.job_queue.run_once(
            close_quiz,
            15,
            chat_id=update.effective_chat.id,
            data=msg.message_id
        )

    except Exception as e:
        await update.message.reply_text("⚠️ An error occurred. Please try again later.")
        print(f"Error in quiz: {e}")

async def close_quiz(context: CallbackContext):
    job = context.job
    await context.bot.edit_message_text(
        "⌛ Time's up!",
        chat_id=job.chat_id,
        message_id=job.data
    )

async def handle_answer(update: Update, context: CallbackContext):
    query = update.callback_query
    _, chosen_idx, correct_idx = query.data.split('_')
    
    if int(chosen_idx) == int(correct_idx):
        update_score(query.from_user.id, query.message.chat.id, 1, update)
        await query.answer("✅ Correct! +1 point")
    else:
        correct_option = json.loads(fetch_questions()[0][1])[int(correct_idx)]
        await query.answer(f"❌ Wrong! Correct: {correct_option}")
    
    await query.edit_message_reply_markup(reply_markup=None)

async def leaderboard(update: Update, context: CallbackContext):
    conn = sqlite3.connect('quiz_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.user_id, 
               COALESCE(u.username, u.first_name || ' ' || COALESCE(u.last_name, '')) AS display_name,
               s.score 
        FROM scores s
        JOIN users u ON s.user_id = u.user_id
        WHERE s.chat_id = ?
        ORDER BY s.score DESC
        LIMIT 10
    ''', (update.effective_chat.id,))
    
    top_users = cursor.fetchall()
    conn.close()

    leaderboard_text = "🏆 Leaderboard:\n" + "\n".join(
        f"{i+1}. {display_name.strip()}: {score} pts"
        for i, (user_id, display_name, score) in enumerate(top_users)
    )
    await update.message.reply_text(leaderboard_text or "No scores yet!")

# ------ Start Bot ------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^ans_"))

    app.run_polling()

if __name__ == "__main__":
    main()