import os
import json
import sys
import gspread
from google.oauth2.service_account import Credentials

# === Auth ===
service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
creds = Credentials.from_service_account_info(
    service_account_info,
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
)
client = gspread.authorize(creds)

spreadsheet_id = os.environ["SPREADSHEET_ID"]
sheet = client.open_by_key(spreadsheet_id)

# === Config ===
TABS = ["verse_complete", "verse_identify", "trivia"]
VALID_TYPES = {
    "verse_complete",
    "verse_identify",
    "verse_fact",
    "book_fact",
    "character_fact",
    "location_fact",
    "number_fact",
    "general_trivia",
}

questions = []

# === Collect questions ===
for tab_name in TABS:
    ws = sheet.worksheet(tab_name)
    rows = ws.get_all_records()

    for row in rows:
        approved = str(row.get("approved", "")).strip().upper()
        qtype = str(row.get("type", "")).strip()

        # skip unapproved or invalid-type rows
        if approved != "Y" or qtype not in VALID_TYPES:
            continue

        def s(v):
            return "" if v is None else str(v).strip()

        q = {
            "type": s(qtype),
            "question": s(row.get("question")),
            "answer": s(row.get("answer")),
            "difficulty": s(row.get("difficulty")),
            "book": s(row.get("book")),
            "chapter": s(row.get("chapter")),
            "verse": s(row.get("verse")),
            "booknum": s(row.get("booknum")),
            "uuid": s(row.get("uuid")),
            "approved": approved,
        }

        questions.append(q)

# === Sort canonically ===
def safe_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0

questions.sort(
    key=lambda q: (
        q["type"],
        safe_int(q["booknum"]),
        safe_int(q["chapter"]),
        safe_int(q["verse"]),
        q["question"].lower(),
    )
)

# === Validate UUID uniqueness ===
uuids = [q["uuid"] for q in questions if q["uuid"]]
dupes = sorted({u for u in uuids if uuids.count(u) > 1})

if dupes:
    print("❌ Duplicate UUIDs detected!")
    for d in dupes:
        print(f" - {d}")
    print("❗ Please fix duplicates in the source sheets before re-running.")
    sys.exit(1)

# === Prepare JSON for output ===
fields_to_keep = ["type", "question", "answer", "difficulty", "uuid"]

# Remove unnecessary fields
clean_questions = [
    {k: q[k] for k in fields_to_keep}
    for q in questions
]

# === Save combined JSON ===
os.makedirs("data", exist_ok=True)
out_path = "data/questions.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(clean_questions, f, ensure_ascii=False, indent=2)

print(f"✅ Built {len(clean_questions)} approved questions from {TABS}")
print(f"📘 Sorted by type → booknum → chapter → verse → question")
print("🆔 All UUIDs unique ✔️")
