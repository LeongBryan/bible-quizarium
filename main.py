#!/usr/bin/env python

import asyncio
import json
import random
import sqlite3
import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    filters
)
from datetime import datetime

import logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


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



os.environ["SSL_CERT_FILE"] = "./cacert-2025-02-25.pem"  # SSL fix

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
    
    cursor.execute('''
        INSERT INTO scores (user_id, chat_id, score)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, chat_id) DO UPDATE SET score = score + ?
    ''', (user_id, chat_id, points, points))
    conn.commit()
    conn.close()

async def quiz(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("⚠️ Please specify a category! Example: /quiz science")
        return

    category = context.args[0].lower()
    valid_categories = ['science', 'geography', 'math']
    
    if category not in valid_categories:
        await update.message.reply_text(f"⚠️ Invalid category! Choose from: {', '.join(valid_categories)}")
        return

    questions = fetch_questions(category)
    if len(questions) < 3:
        await update.message.reply_text("⚠️ Not enough questions in this category!")
        return

    # Initialize chat_data if not exists
    if not hasattr(context, 'chat_data'):
        context.chat_data = {}

    context.chat_data['quiz'] = {
        'category': category,
        'current_question': 0,
        'questions': random.sample(questions, 3),
        'correct_answer': None,
        'answered': False,
        'chat_id': update.effective_chat.id  # Store chat_id for timeouts
    }

    await ask_question(context)


async def ask_question(context: CallbackContext):
    try:
        quiz_data = context.chat_data.get('quiz')
        if not quiz_data or quiz_data['current_question'] >= len(quiz_data['questions']):
            return await end_quiz(context)

        question_num = quiz_data['current_question'] + 1
        question, options_json, correct_idx = quiz_data['questions'][quiz_data['current_question']]
        options = json.loads(options_json)
        
        # Store both original and lowercase versions
        quiz_data['correct_answer'] = options[int(correct_idx)].strip()
        quiz_data['correct_answer_lower'] = quiz_data['correct_answer'].lower().strip()
        
        logger.info(f"New question loaded. Correct answer: '{quiz_data['correct_answer']}'")

        quiz_data['answered'] = False

        await context.bot.send_message(
            chat_id=quiz_data['chat_id'],
            text=f"📚 {quiz_data['category'].capitalize()} Quiz (Question {question_num}/3):\n\n"
                 f"{question}\n\n"
                 "⌛ First correct answer wins! (Type your answer)"
        )

        context.job_queue.run_once(
            question_timeout,
            30,
            chat_id=quiz_data['chat_id'],
            data={'chat_id': quiz_data['chat_id']}
        )
    except Exception as e:
        logger.error(f"Error in ask_question: {e}")


async def question_timeout(context: CallbackContext):
    try:
        chat_id = context.job.data['chat_id']
        quiz_data = context.chat_data.get('quiz')
        
        if not quiz_data or quiz_data.get('answered', False):
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⌛ Time's up! Correct answer was: {quiz_data['correct_answer']}\n"
                 "Moving to next question..."
        )

        quiz_data['current_question'] += 1
        await ask_question(context)
    except Exception as e:
        print(f"Error in question_timeout: {e}")

async def handle_text_answer(update: Update, context: CallbackContext):
    try:
        # Debug incoming message
        raw_message = update.message.text
        logger.info(f"Raw message received: '{debug_string(raw_message)}' (length: {len(raw_message)})")
        
        # Verify chat_data exists
        if not hasattr(context, 'chat_data'):
            logger.error("CRITICAL: context has no chat_data attribute!")
            return
        if context.chat_data is None:
            logger.error("CRITICAL: chat_data is None!")
            return
            
        log_quiz_state(context)  # Log complete state before processing
        
        quiz_data = context.chat_data.get('quiz')
        if not quiz_data:
            logger.error("No quiz_data found in chat_data")
            return
            
        # Check if answer already received
        if quiz_data.get('answered', False):
            logger.info("Ignoring answer - question already answered")
            return
            
        # Get and clean answers
        user_answer = update.message.text.strip()
        stored_answer = quiz_data.get('correct_answer', '').strip()
        
        logger.info(f"Comparing answers:\nUser: '{debug_string(user_answer)}'\nCorrect: '{debug_string(stored_answer)}'")
        logger.info(f"Lengths - User: {len(user_answer)}, Correct: {len(stored_answer)}")
        logger.info(f"Lowercase comparison: {user_answer.lower() == stored_answer.lower()}")
        logger.info(f"Exact comparison: {user_answer == stored_answer}")
        
        # Flexible comparison with multiple checks
        if (user_answer.lower() == stored_answer.lower() or 
            user_answer.casefold() == stored_answer.casefold()):
            
            quiz_data['answered'] = True
            update_score(update.effective_user.id, update.effective_chat.id, 1, update)
            
            logger.info("Answer matched! Processing correct answer")
            
            await update.message.reply_text(
                f"🎉 @{update.effective_user.username} got it right!\n"
                f"Correct answer: {stored_answer}\n"
                "Moving to next question..."
            )
            
            quiz_data['current_question'] += 1
            await ask_question(context)
        else:
            logger.info("Answer didn't match (silently ignored)")
            
    except Exception as e:
        logger.error(f"Exception in handle_text_answer: {str(e)}", exc_info=True)

async def end_quiz(context: CallbackContext):
    quiz_data = context.chat_data.pop('quiz', None)
    if not quiz_data:
        return

    await context.bot.send_message(
        chat_id=quiz_data['chat_id'],
        text="🎉 Quiz complete!\nCheck /leaderboard to see scores!"
    )

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

async def debug_all_messages(update: Update, context: CallbackContext):
    print(f"\nRAW MESSAGE RECEIVED: {update.message.text}")
    print(f"Message ID: {update.message.message_id}")
    print(f"Chat ID: {update.message.chat.id}")
    print(f"User: {update.effective_user.username}")
    
    # Then call your actual handler
    await handle_text_answer(update, context)

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("quiz", quiz))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_answer))

    # Debug: Print all registered handlers
    def print_handlers():
        print("\nRegistered Handlers:")
        for handler in application.handlers:
            print(f"Group {handler}:")
            for h in application.handlers[handler]:
                print(f"  - {h.callback.__name__}")
    
    application.add_handler(MessageHandler(filters.ALL, debug_all_messages), group=99)

    # ... [add your handlers as above] ...
    print_handlers()  # Debug output

    print("Bot is running and waiting for messages...")
    application.run_polling()

if __name__ == "__main__":
    main()