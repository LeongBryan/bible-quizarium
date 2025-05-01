
import sqlite3

def init_db():
    conn = sqlite3.connect('quiz_bot.db')
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY,
            question TEXT,
            options TEXT,  -- JSON-like: ["A", "B", "C"]
            correct_answer INTEGER,
            category TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scores (
            user_id INTEGER,
            chat_id INTEGER,
            score INTEGER,
            PRIMARY KEY (user_id, chat_id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Add sample questions (run once)
def add_sample_questions():
    conn = sqlite3.connect('quiz_bot.db')
    cursor = conn.cursor()
    sample_questions = [
        ("What is the capital of France?", '["Berlin", "Madrid", "Paris", "Rome"]', 2, "geography"),
        ("Which planet is the Red Planet?", '["Venus", "Mars", "Jupiter", "Saturn"]', 1, "science")
    ]
    cursor.executemany('INSERT INTO questions VALUES (NULL, ?, ?, ?, ?)', sample_questions)
    conn.commit()
    conn.close()

init_db()
# add_sample_questions()  # Run once to populate