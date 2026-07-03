# AI-Powered Database Query Optimizer

An AI agent that analyzes SQL queries, detects performance bottlenecks, recommends indexing strategies and query rewrites, and predicts deployment impact — before queries hit production.

## Features

- **SQL parsing** — Extracts tables, columns, joins, filters, and sort/group patterns (PostgreSQL, MySQL, SQLite, SQL Server, and more via sqlglot)
- **Bottleneck detection** — Rule-based detection of 14+ anti-patterns (full table scans, `SELECT *`, Cartesian joins, correlated subqueries, `OFFSET` pagination, etc.)
- **Index advisor** — Suggests single and composite indexes, skipping columns already covered
- **Query optimizer** — Actionable rewrite recommendations with estimated impact
- **Performance predictor** — Complexity score (0–100), risk level, and projected improvement after fixes
- **AI enrichment** — Optional OpenAI-powered summary and recommendations (falls back to rule-based when no API key)

## Quick Start

### 1. Install dependencies

```bash
cd "ai power optimiztion"
pip install -r requirements.txt
```

### 2. Configure (optional)

Copy `.env.example` to `.env` and set your OpenAI key for AI-powered summaries:

```bash
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

### 3. Run the API server

```bash
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000/docs** for the interactive API.

### 4. Analyze from the CLI

```bash
python -m src.cli "SELECT * FROM orders WHERE status = 'pending' ORDER BY created_at"
```

With table size context:

```bash
python -m src.cli -f examples/slow_query.sql --table-sizes "{\"orders\": 500000}" --json
```

## API Usage

**POST** `/analyze`

```json
{
  "query": "SELECT * FROM users u JOIN orders o ON u.id = o.user_id WHERE u.email LIKE '%@gmail.com'",
  "dialect": "postgres",
  "table_sizes": { "users": 200000, "orders": 1500000 },
  "existing_indexes": {
    "users": [["id"], ["email"]],
    "orders": [["user_id"]]
  },
  "use_ai": true
}
```

Response includes:

| Field | Description |
|-------|-------------|
| `parsed` | Structured query metadata |
| `bottlenecks` | Detected issues with severity and suggestions |
| `index_recommendations` | `CREATE INDEX` statements with priority |
| `optimizations` | Query rewrite recommendations |
| `performance` | Complexity score, risk level, projected improvement |
| `optimized_query` | Suggested rewritten SQL (when applicable) |
| `ai_summary` | Executive summary (AI or fallback) |

## Architecture

```
SQL Query
    │
    ▼
┌─────────────┐
│  SQL Parser │  sqlglot AST → ParsedQuery
└──────┬──────┘
       │
       ▼
┌──────────────────┐     ┌──────────────┐
│ Bottleneck       │────▶│ Index Advisor│
│ Detector         │     └──────────────┘
└──────┬───────────┘
       │
       ▼
┌──────────────────┐     ┌────────────────────┐
│ Query Optimizer  │────▶│ Performance        │
│                  │     │ Predictor          │
└──────┬───────────┘     └────────────────────┘
       │
       ▼
┌──────────────────┐
│ AI Agent (opt.)  │  OpenAI enrichment
└──────────────────┘
```

## Example Output

For a slow query like:

```sql
SELECT * FROM orders
WHERE LOWER(email) = 'user@example.com'
ORDER BY created_at DESC
OFFSET 10000 LIMIT 20;
```

The agent detects:

- `SELECT *` — unnecessary column fetch
- Function on column — `LOWER(email)` blocks index use
- `ORDER BY` without `LIMIT` context / missing covering index
- Large `OFFSET` pagination

And recommends indexes, rewrites (`email = LOWER(:input)`), and keyset pagination.

## Project Structure

```
src/
├── main.py              # FastAPI app
├── cli.py               # Command-line interface
├── config.py            # Settings (env vars)
├── agent/
│   ├── orchestrator.py  # Analysis pipeline
│   └── ai_agent.py      # OpenAI integration
├── analyzer/
│   ├── bottleneck_detector.py
│   ├── index_advisor.py
│   ├── query_optimizer.py
│   └── performance_predictor.py
├── parser/
│   └── sql_parser.py
└── models/
    └── schemas.py       # Pydantic models
```

## License

MIT
