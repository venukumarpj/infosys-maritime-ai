# FreightQuote AI Copilot — Colab Integration Guide

This guide explains how to add the **Step 7 AI Copilot** to the FreightQuote Milestone 2 project in Google Colab.

The Copilot in this milestone is a small, database-backed assistant. It supports greetings and predefined question patterns. It does **not** use an LLM or RAG. Answers must come from SQL queries against the project database.

## 1. Files you need

Make sure these project files are available:

- `server.py`
- `db.py`
- `seed_data.py`
- `config.py`
- `live_engine.py`
- `blocks.py`
- `analyst.py`
- **`AI Copilot module.py`** — the combined Copilot module containing the 30 question patterns

Keep the Copilot file in the project folder, for example `/content/app/`.

> The filename contains spaces. The import instructions below use Python's `importlib` so you do not need to rename it.

## 2. Open the project in Google Colab

1. Open the project notebook in Google Colab.
2. Run the cells that install the project's required packages.
3. Make sure the project files are available under `/content/app/`.

If your files are on your computer, upload them using:

```python
from google.colab import files
uploaded = files.upload()
```

If the uploaded Copilot file is in the notebook's current directory, copy it into the project folder:

```python
import os
import shutil

os.makedirs("/content/app", exist_ok=True)
shutil.copy(
    "AI Copilot module.py",
    "/content/app/AI Copilot module.py"
)
```

If Colab reports that the source file cannot be found, check the filename shown by `files.upload()` and use that exact name.

## 3. Select the Freight project before importing project modules

The project configuration chooses the database using `APP_KIND`. Set it to `Freight` **before importing** `config`, `db`, `seed_data`, or `live_engine`.

```python
import os
os.environ["APP_KIND"] = "Freight"

import sys
if "/content/app" not in sys.path:
    sys.path.insert(0, "/content/app")
```

If you already imported project modules before setting `APP_KIND`, restart the Colab runtime and run this step first. This avoids modules retaining a previously selected database path.

## 4. Initialize the Freight database

Run the project's own initialization and seed functions. Do not create an empty database file manually.

```python
import config
import db
import seed_data
import live_engine as LE

print("Project type:", config.KIND)
print("Database path:", config.DB_PATH)

db.init_db()
seed_data.seed_all()
LE.init_live_tables()

print("Database initialized.")
```

Confirm that `Project type` is `Freight` and that the database path ends in `freight_database.db`.

If the notebook's project uses a different initialization sequence, follow the existing project startup cell or the `_boot()` function in `server.py`. The important point is that the Freight database and its tables must be initialized before Copilot queries are tested.

## 5. Load the Copilot module

The filename has spaces, so load it with `importlib`:

```python
import importlib.util
import sys

COPILOT_FILE = "/content/app/AI Copilot module.py"

spec = importlib.util.spec_from_file_location("COPILOT", COPILOT_FILE)
COPILOT = importlib.util.module_from_spec(spec)
sys.modules["COPILOT"] = COPILOT
spec.loader.exec_module(COPILOT)

print("Copilot module loaded.")
```

The module imports `Q` from `blocks.py`. Make sure `/content/app` is in `sys.path`, `blocks.py` is present, and `live_engine` has been initialized.

## 6. Check that the database contains the expected tables

Before testing all questions, inspect the tables in the active database:

```python
import sqlite3
import config

conn = sqlite3.connect(config.DB_PATH)
tables = conn.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    ORDER BY name
""").fetchall()

print([row[0] for row in tables])
conn.close()
```

The Copilot SQL must match the actual Freight database table and column names. If a question fails with `no such table` or `no such column`, inspect the schema and update that question's SQL to match the project database. Do not replace a failed query with a made-up answer.

## 7. Test one question

Call the function exposed by the Copilot module:

```python
result = COPILOT.answer_copilot(
    "How many shipments are there?",
    user={"role": "Admin"}
)

print(result)
```

Use the exact function signature defined in `AI Copilot module.py` if it differs from this example. In particular, check how the module expects the user's role and identity to be passed.

A successful answer should be based on a database query. The response should include the SQL used and the number of rows returned, as required by the milestone.

## 8. Connect the Copilot to the FastAPI application

Integrate the Copilot at the API layer used by the existing project. Do not remove or replace existing routes, authentication, database logic, or the six existing agents.

At the top of `server.py` (after the project path is available), load the module once:

```python
import importlib.util
import sys

COPILOT_FILE = "/content/app/AI Copilot module.py"
spec = importlib.util.spec_from_file_location("COPILOT", COPILOT_FILE)
COPILOT = importlib.util.module_from_spec(spec)
sys.modules["COPILOT"] = COPILOT
spec.loader.exec_module(COPILOT)
```

Then add a protected Copilot endpoint using the project's existing authentication dependency and request model conventions. The following is a **shape/example**, not a drop-in replacement for your existing auth code:

```python
from fastapi import Depends

# Reuse the project's existing current-user/authentication dependency.
# Reuse or define a Pydantic request model with a `question: str` field.

@app.post("/api/copilot")
def copilot_endpoint(payload: CopilotRequest, user=Depends(get_current_user)):
    return COPILOT.answer_copilot(payload.question, user=user)
```

Replace `CopilotRequest` and `get_current_user` with the actual names already used in your `server.py`. Pass the authenticated user object or dictionary in the format expected by `answer_copilot`.

Do not trust a role or customer ID sent by the browser. Obtain identity and role from the authenticated server-side user.

## 9. Enforce role-based access control

The Copilot must enforce the same role permissions as the rest of the application. At minimum, test these intended access boundaries against the project's role matrix:

| Role | Copilot data access |
|---|---|
| Admin | All permitted project data |
| Operations Manager | Shipments/routes, carriers, weather and customs data |
| Freight Broker | Quotes, carriers and margin-related data |
| Auditor | Read-only access to permitted project data |
| Customer | Only that customer's own shipments and quotes |

Important checks:

- Apply authorization on the server, not only by hiding UI controls.
- Customer queries must be filtered using the authenticated customer's server-side ID.
- If the authenticated customer ID is missing, deny customer-specific data access rather than returning all customers' records.
- Do not allow a user to change their role or customer ID by editing request JSON.
- Keep the existing six agents intact.

The role names and permission checks in the module must match the exact role values used by your authentication code.

## 10. The 30 Copilot question patterns

The combined module is intended to cover these questions:

1. Show all shipments.
2. How many shipments are there?
3. Show delayed shipments.
4. Which shipments have the highest delay risk?
5. Show all freight quotes.
6. What is the total value of freight quotes?
7. Show quotes with low margins.
8. Which carrier has the best on-time performance?
9. Which carrier has the lowest cost index?
10. Show the most congested ports.
11. Which ports have the highest average dwell time?
12. Show current weather risks.
13. Which ports have high weather risk?
14. Show customs rules.
15. Show all customers.
16. How many quotes were generated this month?
17. Which carrier handles the most shipments?
18. Show shipments arriving at Mumbai.
19. Which routes have the highest freight costs?
20. What is the average shipment weight?
21. How many shipments are currently in transit?
22. Show quotes with margins above 20%.
23. Which carrier has the highest risk level?
24. List shipments affected by bad weather.
25. Which destination has the most customs holds?
26. How many quotes are pending?
27. Show the cheapest available route.
28. Which shipments have exceeded their expected delivery date?
29. Show shipments with customs clearance completed.
30. What is the total value of all generated quotes?

The module may also recognize greetings and should politely handle unsupported questions by suggesting three supported questions.

## 11. Test the Copilot

Test every supported question using the correct authenticated role. Record the actual output and verify that the result matches the database.

Suggested test checklist:

- [ ] Greeting receives a friendly response.
- [ ] All 30 question patterns are recognized.
- [ ] Alternate wording and minor spelling mistakes are handled where implemented.
- [ ] Each data answer displays the SQL query.
- [ ] Each data answer displays the number of rows returned.
- [ ] Unsupported questions receive a polite out-of-scope response and three example questions.
- [ ] Each role can access only its permitted data.
- [ ] A Customer can see only their own shipments and quotes.
- [ ] SQL errors are handled safely and do not produce invented figures.
- [ ] Existing authentication, application pages, and six agents still work.

Some SQL patterns may need adjustment to the actual Freight database schema. In particular, verify timestamp fields, status values, weather-risk joins, customs-hold values, and customer ownership fields before treating the test suite as passed.

## 12. Add tested questions and answers to README

For the project submission, document the questions you actually tested and their real outputs. Include:

- The question asked.
- The role used for the test.
- The answer returned.
- The SQL query used.
- The number of rows returned.
- Whether the result was verified against the database.

Do not mark a question as passed until it has been run against the initialized Freight database.

## 13. Troubleshooting

**`FileNotFoundError` for `AI Copilot module.py`**
- Confirm that the file exists at `/content/app/AI Copilot module.py`.
- Check capitalization, spaces, and the `.py` extension.

**`ModuleNotFoundError: blocks`**
- Confirm that `blocks.py` is in `/content/app/`.
- Add `/content/app` to `sys.path` before loading the Copilot module.

**`ModuleNotFoundError` or import errors from project modules**
- Run the project's dependency-installation cells.
- Confirm that project modules are in `/content/app`.
- Restart the runtime and set `APP_KIND="Freight"` before importing them.

**Wrong database is selected**
- Check `config.KIND` and `config.DB_PATH`.
- Set `APP_KIND` before imports; restart the runtime if necessary.

**`no such table` or `no such column`**
- Inspect the actual Freight database schema.
- Update the relevant SQL to use real table and column names.
- Re-run the question and verify its result.

**Customer sees another customer's records**
- Stop testing and fix the authorization filter before using the endpoint.
- Derive the customer ID from the authenticated user and apply it to every relevant query.

## 14. Final handover checklist

- [ ] `AI Copilot module.py` is included in the project files.
- [ ] The notebook selects and initializes the Freight database.
- [ ] The module loads successfully in Colab.
- [ ] The Copilot endpoint uses the existing authentication system.
- [ ] Role-based access and customer data isolation are tested.
- [ ] SQL and row counts are shown for database answers.
- [ ] Unsupported questions are handled politely.
- [ ] Tested questions and real answers are documented in the project README.
- [ ] Existing six agents and other project functionality remain intact.

---

**Implementation note:** This guide describes the integration approach. It does not certify that all 30 SQL statements match your current database schema or that the endpoint is already integrated. Confirm those items by running the tests in your project notebook.
