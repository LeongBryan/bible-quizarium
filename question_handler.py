import json
import random
from pathlib import Path

# Load the JSON file at bot startup
QUESTIONS_FILE = Path("data/questions.json")

with QUESTIONS_FILE.open("r", encoding="utf-8") as f:
    ALL_QUESTIONS = json.load(f)

# Helper to filter questions by user-selected category
def filter_questions(user_category: str):
    """
    user_category: "All", "Trivia", "Verses"
    """
    if user_category.lower() == "all":
        return ALL_QUESTIONS
    elif user_category.lower() == "trivia":
        # All types except verse_complete and verse_identify
        return [q for q in ALL_QUESTIONS if q["type"] not in ("verse_complete", "verse_identify")]
    elif user_category.lower() == "verses":
        return [q for q in ALL_QUESTIONS if q["type"] in ("verse_complete", "verse_identify")]
    else:
        return []  # fallback, empty list

def fetch_questions(category="All", rounds=3):
    """
    Returns a list of tuples: (question, answer, type)
    """
    candidates = filter_questions(category)

    if len(candidates) < rounds:
        return None  # let the bot handle not enough questions

    random.shuffle(candidates)
    selected = candidates[:rounds]

    return [(q["question"], q["answer"], q["type"]) for q in selected]
