import gspread
from oauth2client.service_account import ServiceAccountCredentials
import random

# Google Sheets API setup
def fetch_questions(category="general", rounds=3):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name('./bible-quizarium-93d3f0de44fa.json', scope)
    client = gspread.authorize(creds)

    sheet = client.open("bible_quiz").sheet1
    records = sheet.get_all_records()

    if category and category.lower() != "general":
        records = [r for r in records if r["category"].lower() == category.lower()]

    random.shuffle(records)
    selected = records[:rounds]

    result = []
    for r in selected:
        q = r["questions"]
        a = r["answers"]
        result.append((q, a))
    print(result)
    return result

if __name__ == '__main__':
    fetch_questions("general", 3)  # Example usage, can be removed later