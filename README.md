# bible-quizarium

## Run Locally

### Prerequisite
- Retrieve telegram bot token from admin
- Create file `.env` at root and set variable `TOKEN=xxx`

### Steps
1. Update main.py with token (to be changed)
2. Create own file locally called leaderboard.db
3. Run `python -m pip install -r requirements.txt`
4. Run `python app/main.py` from app directory


## Deploy to Kubernetes local cluster
1. Populate the Secret object with API key
2. Populate the Secret object with postgresDB credentials
3. Create mount path `/mnt/data/postgres`
4. Create Namespace, Deployment, pvc, Secret:
```bash
k create ns bible-quizarium
k -n bible-quizarium apply -f k8s/cnph.yaml
k -n bible-quizarium apply -f k8s/deployment.yaml
k -n bible-quizarium apply -f k8s/pvc.yaml
k -n bible-quizarium apply -f k8s/secres.yaml
```

## TODO:
- questions are repeated sometimes, apparently
- 2 questions back-to-back with same answer just awards 'correct' to both questions. 
- badly needs refactoring
- answers end up lower-case everything. It should display as-is.
 

## GitHub Actions Data Pipeline
### Overview
The repository includes an automated data pipeline that syncs approved questions from Google Sheets into a single JSON file (data/questions.json). This ensures the bot can load questions locally without making live API calls, improving performance and reliability. The logic is in the workflow and uses `./scripts/build_questions.py`

### Workflow
- **Trigger**: Manual only (workflow_dispatch) — only maintainers can run it.
- **Filter**: Only rows with approved == "Y" are included.
- **Sorting order**: type → booknum → chapter → verse → question
On trigger, the workflow creates a commit and pushes directly to the repository at `data/questions.json`

### Validation
- All UUIDs must be unique. If duplicates exist, the workflow fails and highlights the offending UUIDs.
- Only approved (set to "Y") and valid-type questions are pulled into the final JSON.


### Secrets Required

The workflow requires the following repository secrets:
- GOOGLE_SERVICE_ACCOUNT_JSON → service account credentials JSON
- SPREADSHEET_ID → ID of the source Google Sheet

### Notes for Contributors
- Only maintainers should run this workflow manually.
- Ensure new questions have `approved` set to "Y", and then lock those rows.
- The workflow enforces a canonical sort order to keep diffs predictable and maintain version control clarity.