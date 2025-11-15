import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime


class DatabaseManager:
    def __init__(self):
        self.mode = os.getenv("DB_MODE", "sqlite").lower()
        self.url = os.getenv("DATABASE_URL")

        if self.mode not in ("sqlite", "postgres"):
            raise ValueError("DB_MODE must be 'sqlite' or 'postgres'")

        if self.mode == "postgres" and not self.url:
            raise ValueError("DATABASE_URL must be set when DB_MODE=postgres")

        # Create table at startup
        self._init_schema()

    def _get_conn(self):
        if self.mode == "sqlite":
            return sqlite3.connect("leaderboard.db")
        else:
            return psycopg2.connect(self.url, cursor_factory=RealDictCursor)

    def _init_schema(self):
        conn = self._get_conn()
        cur = conn.cursor()

        if self.mode == "sqlite":
            cur.execute('''
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
                )
            ''')
        else:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS scores (
                    user_id BIGINT,
                    chat_id BIGINT,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    total_score INT DEFAULT 0,
                    games_played INT DEFAULT 0,
                    wins INT DEFAULT 0,
                    last_updated TIMESTAMP,
                    PRIMARY KEY (user_id, chat_id)
                )
            ''')

        conn.commit()
        conn.close()

    def save_score(self, user_id, chat_id, username, first_name, last_name, score, is_winner=False):
        conn = self._get_conn()
        cur = conn.cursor()
        win_inc = 1 if is_winner else 0

        if self.mode == "sqlite":
            cur.execute('''
                INSERT INTO scores (user_id, chat_id, username, first_name, last_name, total_score, games_played, wins, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, datetime('now'))
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name,
                    total_score=scores.total_score + excluded.total_score,
                    games_played=scores.games_played + 1,
                    wins=scores.wins + excluded.wins,
                    last_updated=datetime('now')
            ''', (user_id, chat_id, username, first_name, last_name, score, win_inc))
        else:
            cur.execute('''
                INSERT INTO scores (user_id, chat_id, username, first_name, last_name, total_score, games_played, wins, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, 1, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, chat_id) DO UPDATE
                    SET username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        total_score = scores.total_score + EXCLUDED.total_score,
                        games_played = scores.games_played + 1,
                        wins = scores.wins + EXCLUDED.wins,
                        last_updated = CURRENT_TIMESTAMP
            ''', (user_id, chat_id, username, first_name, last_name, score, win_inc))

        conn.commit()
        conn.close()

    def get_leaderboard(self, chat_id, limit=10):
        conn = self._get_conn()
        cur = conn.cursor()

        if self.mode == "sqlite":
            cur.execute(
                "SELECT username, total_score, wins, games_played FROM scores WHERE chat_id=? ORDER BY total_score DESC LIMIT ?",
                (chat_id, limit)
            )
            rows = cur.fetchall()
        else:
            cur.execute(
                "SELECT username, total_score, wins, games_played FROM scores WHERE chat_id=%s ORDER BY total_score DESC LIMIT %s",
                (chat_id, limit)
            )
            rows = cur.fetchall()

        conn.close()
        return rows
