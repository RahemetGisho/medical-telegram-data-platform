# Medical Telegram Data Platform

An end-to-end data engineering pipeline for collecting medical-related Telegram messages, storing them in PostgreSQL, and transforming them into an analytics-ready data warehouse using dbt.

---

## Project Structure

```text
medical-telegram-data-platform/
├── data/
├── notebooks/
├── scripts/
├── src/
├── medical_warehouse/
│   ├── models/
│   ├── tests/
│   ├── macros/
│   ├── dbt_project.yml
│   └── profiles.yml
├── requirements.txt
└── README.md
```
---

# 1: Data Ingestion

### Objective

Collect messages from public Telegram medical channels and store them in PostgreSQL.

### Features

- Scrape Telegram channels
- Extract message metadata
- Capture engagement metrics
- Store raw data in PostgreSQL
---

# 2: Data Warehouse

### Objective

Transform raw data into an analytics-ready star schema using dbt.

### Models

| Model | Description |
|-------|-------------|
| `stg_telegram_messages` | Cleans and standardizes raw messages |
| `dim_channels` | Channel dimension |
| `dim_dates` | Date dimension |
| `fct_messages` | Message fact table |

---

## Data Quality

Implemented using dbt tests:

- `not_null`
- `unique`
- `relationships`
- `accepted_values`
- `dbt_expectations`
- Custom SQL tests
---

## Running the Project

Install dependencies:

```bash
pip install -r requirements.txt
```

Load raw data:

```bash
python src/loader.py
```

Run dbt models:

```bash
cd medical_warehouse
dbt build --profiles-dir .
```

Run tests:

```bash
dbt test --profiles-dir .
```

Generate documentation:

```bash
dbt docs generate
dbt docs serve
```

---

## Technologies

- Python
- PostgreSQL
- Telethon
- SQLAlchemy
- dbt Core
- dbt-postgres
- dbt-expectations
- pandas
- pytest

---
