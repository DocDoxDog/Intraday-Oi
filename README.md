# Intraday OI Analytics

## Overview

Intraday OI Analytics is a Python-based data pipeline that collects, processes, analyzes, and stores intraday Options Open Interest (OI) data from CME QuikStrike.

The system is designed for quantitative research, options flow analysis, and algorithmic trading. It automates data collection, parsing, AI-assisted market analysis, historical storage in Supabase, and Telegram notifications.

## Features

- Automated intraday Open Interest collection
- Historical storage with Supabase
- AI-assisted market summaries
- Telegram notifications
- GitHub Actions automation
- Environment variable configuration

## Project Structure

```text
src/
├── main.py
├── scraper.py
├── parser.py
├── analyze.py
├── history.py
├── supabase_client.py
└── telegram.py

supabase/
└── migrations/

.github/
└── workflows/
```

## Requirements

- Python 3.11+
- Supabase project
- Telegram Bot Token
- Gemini API Key (optional)

## Installation

```bash
git clone <repository>
cd Intraday-Oi

python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file.

```env
SUPABASE_URL=
SUPABASE_KEY=
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=
GEMINI_API_KEY=
```

## Running

```bash
python src/main.py
```

## Workflow

```text
QuikStrike
     │
     ▼
 Scraper
     │
     ▼
 Parser
     │
     ▼
 AI Analysis
     │
     ▼
 Supabase
     │
     ▼
 Telegram
```

## Output

The application stores:

- Intraday Open Interest snapshots
- Historical records
- AI-generated market summaries
- Processed analytics

## Deployment

The project supports scheduled execution through GitHub Actions.

## License

Internal / Commercial Use Only

## Author

Suphadet Boonyarach

Computer Science, Chiang Mai University

Quantitative Trading Research
