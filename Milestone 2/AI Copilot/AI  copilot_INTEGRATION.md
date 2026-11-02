# FreightQuote AI Copilot — Step 7 integration

## Files
- `copilot_step7.py`: 15 additional SQL-only intents (questions 16–30).

## 1. Add the helper to the FastAPI project
Place `copilot_step7.py` in the same folder as `analyst.py`, `qa.py`, and `blocks.py` (the original notebook writes these under `/content/app`).

In the FastAPI notebook, add a code cell before the cell that writes `server.py`:

```python
# Upload copilot_step7.py to Colab, then:
import shutil
shutil.copy('/content/copilot_step7.py', '/content/app/copilot_step7.py')
```

Alternatively, paste the contents of the supplied file into a notebook cell using `%%writefile /content/app/copilot_step7.py`.

## 2. Integrate with the authenticated user
In the `server.py` cell, add this import with the other local imports:

```python
import copilot_step7 as S7
```

Inside `/api/copilot`, `u = user_of(request)` is already present in the Authentication A version. In the `gen()` function, before calling `AN.answer(...)` or `QA.answer(...)`, call:

```python
exact = S7.answer_step7(
    q,
    role=u.get('role', 'Customer'),
    customer_id=u.get('customer_id')
)
if exact is None:
    exact = AN.answer(KIND, q, None, VC.decision(), dom) or QA.answer(KIND, q, None, None)
```

**RBAC integration warning:** This helper enforces the Step 5 domain matrix for its 15 new intents. It also filters Customer shipment/quote data by `customer_id`. The uploaded Authentication A code does not currently select or return `customer_id`, and its `ctx.scope`, `need()`, and `menu_for()` are placeholders. The uploaded Person B notebook is a Streamlit app, not the FastAPI `rbac.py` implementation. Therefore, do not consider full Copilot RBAC complete until the FastAPI user record has a real `customer_id` and Person B's FastAPI RBAC checks are integrated. A Customer without a linked `customer_id` is safely denied by this helper.

## 3. Show the returned row count
The helper returns `rows` and `row_count`. Change the existing SSE exact event from:

```python
yield _sse("exact", sql=exact["sql"], rows=0 if exact["df"] is None else len(exact["df"]))
```

to:

```python
row_count = exact.get('row_count', exact.get('rows', 0 if exact.get('df') is None else len(exact['df'])))
yield _sse("exact", sql=exact.get('sql', ''), rows=row_count)
```

For questions returning a table or aggregate row, the count is the number of rows returned by the SQL statement. Greetings intentionally have no SQL and return zero rows.

## 4. New questions (16–30)
1. How many quotes were generated this month?
2. Which carrier handles the most shipments?
3. Show shipments arriving at Mumbai.
4. Which routes have the highest freight costs?
5. What is the average shipment weight?
6. How many shipments are currently in transit?
7. Show quotes with margins above 20%.
8. Which carrier has the highest risk score?
9. List shipments affected by bad weather.
10. Which destination has the most customs holds?
11. How many quotes are pending?
12. Show the cheapest available route.
13. Which shipments have exceeded their expected delivery date?
14. Show shipments with customs clearance completed.
15. What is the total value of all generated quotes?

## 5. Validation before README claims
Run each question against the actual seeded SQLite database. Confirm that the query succeeds and that the result is sensible. Record the actual result and row count in the README; do not write sample or guessed numeric answers as if they were observed.
