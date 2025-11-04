#!/usr/bin/env python

import json
import random
import sqlite3
import os
from dotenv import load_dotenv
from apscheduler.jobstores.base import JobLookupError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, User
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    CallbackQueryHandler,
    filters
)
from datetime import datetime

import logging
from logging.handlers import TimedRotatingFileHandler

import question_handler as question_handler

# Create logger
logger = logging.getLogger("quizbot")
logger.setLevel(logging.INFO)
logger.propagate = False  # Prevent double logging if root logger is used

# Formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Console Handler (optional)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Daily Rotating File Handler
file_handler = TimedRotatingFileHandler(
    "quizbot.log",             # Log file base name
    when="midnight",           # Rotate at midnight
    interval=1,                # Every day
    backupCount=7,             # Keep last 7 days of logs
    encoding='utf-8',
    utc=True                   # Optional: use UTC time; remove if you prefer local
)
file_handler.setFormatter(formatter)

# Add handlers
logger.addHandler(console_handler)
logger.addHandler(file_handler)

os.environ["SSL_CERT_FILE"] = "./cacert-2025-02-25.pem"  # SSL fix

load_dotenv()
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("Telegram token not set! Add it to your .env file")

VALID_CATEGORIES = ['All', 'Trivia', 'Verses']
TYPE_LABELS = {
    "verse_complete": "Complete the verse",
    "verse_identify": "Identify the verse",
    "verse_fact": "Trivia",
    "book_fact": "Trivia",
    "character_fact": "Trivia",
    "location_fact": "Trivia",
    "number_fact": "Trivia",
    "general_trivia": "Trivia"
}


### DEBUGGING ###############################################################
def debug_string(s):
    """Show invisible characters in strings"""
    return ''.join(f'\\x{ord(c):02x}' if ord(c) < 32 or ord(c) > 126 else c for c in s)

def log_quiz_state(context):
    """Log the complete quiz state"""
    if not hasattr(context, 'chat_data'):
        logger.info("No chat_data exists")
        return
    quiz_data = context.chat_data.get('quiz')
    if not quiz_data:
        logger.info("No quiz_data exists")
        return
    logger.info(f"Quiz State: {json.dumps(quiz_data, indent=2, default=str)}")
### DEBUGGING ###############################################################



##############
# START QUIZ #
##############

async def start(update: Update, context: CallbackContext):
    if context.chat_data.get("quiz") or context.chat_data.get("quiz_setup_pending"): # prevent concurrent quiz setup
        await update.message.reply_text("⚠️ A quiz is already being set up or in progress. Please finish it first.")
        return

    context.chat_data["quiz_setup_pending"] = True  # Set flag early to avoid race conditions

    keyboard = [
        [InlineKeyboardButton(cat.capitalize(), callback_data=f"select_category:{cat}")]
        for cat in VALID_CATEGORIES
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📚 Choose a category:", reply_markup=reply_markup)


# Callback query handler for category selection
async def handle_category_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data

    if not data.startswith("select_category:"):
        return

    category = data.split(":")[1]
    context.user_data["selected_category"] = category

    # Prompt for number of rounds
    keyboard = [
        [InlineKeyboardButton("1 Round", callback_data="select_rounds:1")],
        [InlineKeyboardButton("3 Rounds", callback_data="select_rounds:3")],
        [InlineKeyboardButton("5 Rounds", callback_data="select_rounds:5")],
        [InlineKeyboardButton("10 Rounds", callback_data="select_rounds:10")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"✅ Category selected: *{category.title()}*\n🎯 Now choose number of rounds:",
                                  parse_mode="Markdown",
                                  reply_markup=reply_markup)

async def handle_round_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data

    if not data.startswith("select_rounds:"):
        return

    rounds = int(data.split(":")[1])
    category = context.user_data.get("selected_category")

    if not category:
        await query.edit_message_text("⚠️ Missing category. Please use /quiz again.")
        return

    await query.edit_message_text(f"🧠 Starting quiz: *{category.title()}*, {rounds} rounds!",
                                  parse_mode="Markdown")

    await start_quiz(update, context, category, rounds)


# Actual logic to start the quiz (reused for both direct /quiz and button press)
async def start_quiz(update: Update, context: CallbackContext, category: str, rounds: int):
    context.chat_data.pop("quiz_setup_pending", None)

    # questions is a list of tuples: (question, answer, type)
    questions = question_handler.fetch_questions(category, rounds) 
    
    if len(questions) < rounds:
        await update.effective_message.reply_text("⚠️ Not enough questions in this category!")
        return

    context.chat_data['quiz'] = {
        'category': category,
        'current_question': 0,
        'questions': questions,
        'correct_answer': None,
        'answer_progress': None,
        'answered': False,
        'chat_id': update.effective_chat.id,
        'rounds': rounds,
        'hint_level': 0,
        'score_map': {0: 5, 1: 3, 2: 2, 3: 1}  # based on which 8-sec interval it's answered
    }

    await ask_question(context, context.chat_data['quiz'])

##################
# SCORE HANDLING #
##################

def update_score(context: CallbackContext, user: User, points: int):
    quiz_data = context.chat_data.get("quiz")
    if not quiz_data:
        return

    scores = quiz_data.setdefault("scores", {})

    if user.id not in scores:
        scores[user.id] = {
            "username": user.username or "",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "score": 0
        }

    scores[user.id]["score"] += points


def save_game_score(user_id, chat_id, username, first_name, last_name, score, is_winner=False):
    conn = sqlite3.connect("leaderboard.db")
    cursor = conn.cursor()

    # Ensure table exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scores (
            user_id INTEGER,
            chat_id INTEGER,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            total_score INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            last_updated TEXT,
            PRIMARY KEY (user_id, chat_id)
        );
    ''')

    now = datetime.utcnow().isoformat()
    win_increment = 1 if is_winner else 0

    # Try to update existing record
    cursor.execute('''
        UPDATE scores
        SET
            username = ?,
            first_name = ?,
            last_name = ?,
            total_score = total_score + ?,
            games_played = games_played + 1,
            wins = wins + ?,
            last_updated = ?
        WHERE user_id = ? AND chat_id = ?
    ''', (username, first_name, last_name, score, win_increment, now, user_id, chat_id))

    if cursor.rowcount == 0:
        # Insert new record
        cursor.execute('''
            INSERT INTO scores (
                user_id, chat_id, username, first_name, last_name,
                total_score, games_played, wins, last_updated
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        ''', (user_id, chat_id, username, first_name, last_name, score, win_increment, now))

    conn.commit()
    conn.close()



#####################
# QUESTION HANDLING #
#####################

async def ask_question(context: CallbackContext, quiz_data: dict):
    print("GOT HERE")
    # quiz_data = context.chat_data.get("quiz")
    if not quiz_data:
        print("~ No quiz_data provided ~")        
        return

    # Cancel any existing hint jobs and timeout job to avoid interference
    for job in quiz_data.get("hint_jobs", []):
        try:
            job.schedule_removal()
        except JobLookupError:
            pass
    quiz_data["hint_jobs"] = []
    

    timeout_job = quiz_data.get("timeout_job")
    if timeout_job:
        try:
            timeout_job.schedule_removal()
        except JobLookupError:
            pass
    quiz_data["timeout_job"] = None

    current = quiz_data["current_question"]
    total = quiz_data["rounds"]
    if current >= total:
        await end_quiz(context, quiz_data)
        return

    question, answer, question_type = quiz_data["questions"][current]
    quiz_data["correct_answer"] = answer.strip().lower()
    quiz_data["answered"] = False
    quiz_data["hint_level"] = 0
    quiz_data["start_time"] = datetime.now()

    # Build masked answer
    masked = ["_" if ch.isalnum() else ch for ch in answer]
    quiz_data["masked"] = masked

    # Show initial question and blanked answer
    await context.bot.send_message(
        chat_id=quiz_data["chat_id"],
        text=f"🧠 *Question {current+1}/{total} [{TYPE_LABELS.get(question_type)}]*\n\n"
             f"{question}\n\n"
             f"`{' '.join(masked)}`",
        parse_mode="Markdown"
    )

    # Schedule hint jobs at 8s, 16s, 24s
    job_refs = []
    for i, delay in enumerate([8, 16, 24], start=1):
        job = context.job_queue.run_once(send_hint, delay, data={'level': i, 'chat_id': quiz_data["chat_id"]})
        job_refs.append(job)

    # Schedule final timeout
    timeout = context.job_queue.run_once(question_timeout, 30, data={'chat_id': quiz_data["chat_id"]})

    # Store jobs to cancel later
    quiz_data["hint_jobs"] = job_refs
    quiz_data["timeout_job"] = timeout


async def send_hint(context: CallbackContext):
    level = context.job.data["level"]
    chat_id = context.job.data["chat_id"]
    chat_data = context.application.chat_data.get(chat_id, {})
    quiz_data = chat_data.get("quiz")

    if not quiz_data or quiz_data.get("answered"):
        return

    answer = quiz_data["correct_answer"]
    masked = quiz_data["masked"]

    # Cap hint levels for short answers
    max_hint_level = 3
    if len(answer) < 3:
        max_hint_level = 1
    if level > max_hint_level:
        return  # do not reveal further hints

    indices = [i for i, c in enumerate(masked) if c == "_"]

    # Reveal 30% of remaining characters (at least 1)
    to_reveal = max(1, round(0.3 * len(indices)))
    reveal_indices = random.sample(indices, min(to_reveal, len(indices)))

    for i in reveal_indices:
        masked[i] = answer[i]

    quiz_data["hint_level"] = level
    quiz_data["masked"] = masked

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"💡 Hint {level}/{max_hint_level}:\n`{' '.join(masked)}`",
        parse_mode="Markdown"
    )


async def question_timeout(context: CallbackContext):
    print("⌛ Timeout triggered")
    chat_id   = context.job.data["chat_id"]
    chat_data = context.application.chat_data.get(chat_id, {})
    quiz_data = chat_data.get("quiz")

    # if quiz was already answered or missing, do nothing
    if not quiz_data or quiz_data.get("answered"):
        return

    # mark this round finished
    quiz_data["answered"] = True
    answer = quiz_data["correct_answer"]

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⌛ Time's up! The correct answer was: *{answer}*",
        parse_mode="Markdown"
    )

    # advance the index
    quiz_data["current_question"] += 1

    # 👉 if we've reached (or passed) total rounds, end the quiz
    if quiz_data["current_question"] >= quiz_data["rounds"]:
        await end_quiz(context, quiz_data)           # or end_quiz(context, quiz_data) if your signature needs it
        return

    # otherwise ask the next question
    await ask_question(context, quiz_data)



def is_answer_correct(user_answer: str, correct_answer: str) -> bool:
    if not user_answer or not correct_answer:
        return False
    # Normalize and compare
    return user_answer.strip().lower() == correct_answer.strip().lower()


async def handle_text_answer(update: Update, context: CallbackContext):
    chat_data = context.chat_data  # per-chat context
    quiz_data = chat_data.get("quiz")

    if not quiz_data:
        print("❌ No quiz_data found")
        return

    if not update.message or not update.message.text:
        print("⚠️ No message text received")
        return

    user_answer = update.message.text
    correct_answer = quiz_data.get("correct_answer")

    print(f"✅ Received answer: {user_answer}")
    print(f"✅ Expected answer: {correct_answer}")

    if is_answer_correct(user_answer, correct_answer):
        quiz_data["answered"] = True
        
        for job in quiz_data.get("hint_jobs", []):
            try:
                job.schedule_removal()
            except JobLookupError:
                pass
        quiz_data["hint_jobs"] = []

        timeout_job = quiz_data.get("timeout_job")
        if timeout_job:
            try:
                timeout_job.schedule_removal()
            except JobLookupError:
                pass
        quiz_data["timeout_job"] = None
        
        hint_level = quiz_data.get("hint_level", 0)
        score_map = quiz_data.get("score_map", {0: 5, 1: 3, 2: 2, 3: 1})
        score = score_map.get(hint_level, 1)

        update_score(context, update.effective_user, score)

        await update.message.reply_text(
            f"🎉 @{update.effective_user.username or update.effective_user.first_name} got it right!\n"
            f"✅ Answer: {correct_answer}\n"
            f"🏅 Points: {score}\n"
        )

        quiz_data["current_question"] += 1
        await ask_question(context, quiz_data)
    else:
        print("❌ Incorrect answer (ignored)")



############
# END QUIZ #
############
async def end_quiz(context: CallbackContext, quiz_data: dict):
    # Optional cleanup
    context.application.chat_data.get(quiz_data["chat_id"], {}).pop("quiz_setup_pending", None)
    context.application.chat_data.get(quiz_data["chat_id"], {}).pop("quiz", None)

    chat_id = quiz_data["chat_id"]
    scores = quiz_data.get("scores", {})

    if not scores:
        await context.bot.send_message(
            chat_id=chat_id,
            text="🛑 Quiz ended. No one scored any points!"
        )
        return

    # Sort scores by score descending
    sorted_scores = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
    top_score = sorted_scores[0][1]["score"]
    winners = [user_id for user_id, data in sorted_scores if data["score"] == top_score]

    lines = []
    for user_id, data in sorted_scores:
        username = data.get("username") or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        display = f"@{username}" if username.startswith("@") else username
        score = data["score"]

        # 🏆 Emoji only for winners
        prefix = "🏆" if user_id in winners else "🏅"
        lines.append(f"{prefix} {display}: {score} point{'s' if score != 1 else ''}")

        save_game_score(
            user_id=user_id,
            chat_id=chat_id,
            username=data.get("username", ""),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            score=score,
            is_winner=user_id in winners  # pass True/False
        )

    leaderboard_text = "\n".join(lines)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎉 Quiz complete!\n\n{leaderboard_text}\n\n📊 Check /leaderboard for all-time stats!"
    )




###############
# LEADERBOARD #
###############

import pandas as pd
from telegram import Update
from telegram.ext import CallbackContext
import sqlite3

async def leaderboard(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id

    # Load scores from DB
    conn = sqlite3.connect("leaderboard.db")
    df = pd.read_sql_query(
        "SELECT * FROM scores WHERE chat_id = ?", conn, params=(chat_id,)
    )
    conn.close()

    if df.empty:
        await update.message.reply_text("No leaderboard data yet! Play a quiz to get started.")
        return

    # Construct display_name: use username if present, otherwise fall back to first + last name
    df["display_name"] = df["username"].fillna("")
    fallback_names = (df["first_name"].fillna("") + " " + df["last_name"].fillna("")).str.strip()
    df["display_name"] = df["display_name"].mask(df["display_name"] == "", fallback_names)

    # 🏆 Top Total Scores
    top_total = df.sort_values("total_score", ascending=False).head(5).reset_index(drop=True)
    total_text = "\n".join(
        f"{i+1}. {row['display_name']}: {row['total_score']} pts"
        for i, row in top_total.iterrows()
    )


    # 🥇 Top Wins
    top_wins = df.sort_values("wins", ascending=False).head(5).reset_index(drop=True)
    wins_text = "\n".join(
        f"{i+1}. {row['display_name']}: {row['wins']} wins"
        for i, row in top_wins.iterrows()
    )

    # 🎮 Most Games Played
    top_games = df.sort_values("games_played", ascending=False).head(5).reset_index(drop=True)
    games_text = "\n".join(
        f"{i+1}. {row['display_name']}: {row['games_played']} games"
        for i, row in top_games.iterrows()
    )
    
    leaderboard_message = (
        "📊 *Quiz Leaderboard*\n\n"
        "🏆 *All-time Points:*\n" + total_text + "\n\n" +
        "🥇 *Most Wins:*\n" + wins_text + "\n\n" +
        "🎮 *Most Games Played:*\n" + games_text
    )

    await update.message.reply_text(leaderboard_message, parse_mode="Markdown")


async def log_all_messages(update: Update, context: CallbackContext):
    user = update.effective_user
    chat = update.effective_chat
    message = update.message

    logger.info("📥 RAW MESSAGE RECEIVED")
    logger.info(f"Message ID: {message.message_id}")
    logger.info(f"Chat ID: {chat.id}")
    logger.info(f"User: {user.username} (ID: {user.id})")
    logger.info(f"Text: {message.text}")

    # Forward to actual handler
    await handle_text_answer(update, context)



def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CallbackQueryHandler(handle_category_selection, pattern="^select_category:"))
    application.add_handler(CallbackQueryHandler(handle_round_selection, pattern="^select_rounds:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_answer))

    # Debug: Print all registered handlers
    def print_handlers():
        print("\nRegistered Handlers:")
        for handler in application.handlers:
            print(f"Group {handler}:")
            for h in application.handlers[handler]:
                print(f"  - {h.callback.__name__}")
    
    application.add_handler(MessageHandler(filters.ALL, log_all_messages), group=99)

    # ... [add your handlers as above] ...
    print_handlers()  # Debug output

    print("Bot is running and waiting for messages...")
    application.run_polling()

if __name__ == "__main__":
    main()