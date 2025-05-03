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
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scores (
            user_id INTEGER,
            chat_id INTEGER,
            score INTEGER,
            PRIMARY KEY (user_id, chat_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

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

# New function to update user info
def update_user(user_id, username=None, first_name=None, last_name=None):
    conn = sqlite3.connect('quiz_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (user_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            last_updated = CURRENT_TIMESTAMP
    ''', (user_id, username, first_name, last_name))
    conn.commit()
    conn.close()

init_db()
# add_sample_questions()  # Run once to populate