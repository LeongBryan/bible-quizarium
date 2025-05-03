import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Google Sheets API setup
def get_questions_from_sheet():
    # Use the credentials.json file you downloaded
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name('./bible-quizarium-93d3f0de44fa.json', scope)
    client = gspread.authorize(creds)
    
    # Open your Google Sheet by name or URL
    sheet = client.open("bible_quiz").sheet1  # or .get_worksheet(0) for index
    questions = sheet.col_values(1)  # Assuming questions are in the first column
    print(questions)
    return questions


if __name__ == '__main__':
    get_questions_from_sheet()