# Packbot – Pokemon TCG Scanner

A web-based Pokemon TCG card scanner and collection manager.

## Features

- **Camera scanning** – Capture card photos via webcam
- **Manual lookup** – Identify cards by name, set code, or collector number
- **TCG API integration** – Live card data and market prices via [pokemontcg.io](https://pokemontcg.io)
- **Collection manager** – Track cards by condition, quantity, and foil status
- **Scan history** – Review all previously scanned cards

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment (optional – adds rate-limit API key)
cp .env.example .env
# Edit .env and add your POKEMON_TCG_API_KEY

# 3. Run
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/scan/image` | Identify card from camera image + hints |
| POST | `/api/scan/text` | Identify card from free-form text |
| GET | `/api/cards/search?q=...` | Search TCG API cards |
| GET | `/api/cards/<id>` | Fetch single card detail |
| GET | `/api/cards/<id>/price` | Fetch market prices |
| GET | `/api/sets` | List all TCG sets |
| GET | `/api/collection` | Get your collection |
| POST | `/api/collection` | Add card to collection |
| DELETE | `/api/collection/<id>` | Remove collection entry |
| GET | `/api/collection/stats` | Collection statistics |
| GET | `/api/scans` | Scan history |

## Scan Request Body

```json
{
  "image": "<base64 data URL from canvas>",
  "pokemon_name": "Charizard",
  "set_code": "base1",
  "card_number": "4"
}
```

## Card Conditions

| Code | Meaning |
|------|---------|
| NM | Near Mint |
| LP | Lightly Played |
| MP | Moderately Played |
| HP | Heavily Played |
| DMG | Damaged |

## Architecture

```
app.py          Flask application + REST API routes
scanner.py      Card identification logic
tcg_api.py      Pokemon TCG API client
database.py     SQLite persistence layer
static/
  index.html    Single-page frontend
  style.css     Dark-theme stylesheet
  app.js        Frontend application logic
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POKEMON_TCG_API_KEY` | (none) | API key for higher rate limits |
| `FLASK_SECRET_KEY` | dev key | Flask session secret |
| `FLASK_DEBUG` | false | Enable debug mode |
| `DATABASE_PATH` | packbot.db | SQLite file path |
| `PORT` | 5000 | Server port |
