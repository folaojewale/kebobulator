# Kebobulator

A kebab consumption tracker and year-end prediction tool with Discord integration. Track how many kebabs someone has eaten this year, project their full-year total, and rank a group of guessers by how close their predictions are.

## How It Works

Given the number of kebabs eaten so far this year, Kebobulator finds a projected year-end total based on the current daily rate. It then scores each person's guess and are ranked by how close they are to the projection (closest = highest score, up to 99%).

Kebab counts can be entered manually or auto-counted from images posted in a Discord channel (on the assumption that each image = one kebab).

## Files

| File | Purpose |
|---|---|
| `kebobulator.py` | Core logic + interactive CLI script |
| `kebobulator_bot.py` | Discord bot that auto-posts updates whenever a new image is posted |
| `values.csv` | List of participants and their year-end guesses |
| `requirements.txt` | Python dependencies |

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create a `.env` file

```env
DISCORD_BOT_TOKEN=your.bot.token.here
DISCORD_CHANNEL_ID=123456789012345678
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

- **`DISCORD_BOT_TOKEN`** — Bot token from the [Discord Developer Portal](https://discord.com/developers/applications) (Application → Bot → Token). The bot needs **View Channel** and **Read Message History** permissions on the target channel.
- **`DISCORD_CHANNEL_ID`** — Numeric ID of the channel where kebab images are posted. (Right-click the channel in Discord → Copy Channel ID, with Developer Mode enabled.)
- **`DISCORD_WEBHOOK_URL`** — Webhook URL for the channel where prediction updates should be posted. (Channel Settings → Integrations → Webhooks.)

`DISCORD_WEBHOOK_URL` is optional for the CLI — without it, results are printed to the terminal only.

### 3. Update `values.csv`

Add or edit participant guesses. The file must have `name` and `value` columns:

```csv
name,value
Alice,200
Bob,175
```

## Usage

### Interactive CLI

```bash
python kebobulator.py
```

You'll be prompted for:

- **As-of date** — the date up to which kebabs have been counted (defaults to today).
- **Kebab count** — enter a number, or press Enter to auto-count images from the Discord channel (requires `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` in `.env`).

Results are printed to the terminal. If `DISCORD_WEBHOOK_URL` is set, the update is also posted to Discord.

### Discord Bot (live updates)

```bash
python kebobulator_bot.py
```

The bot watches the configured channel and automatically posts a prediction update to the webhook whenever a new image is posted. It requires all three environment variables to be set.

## Scoring

- Guesses **above** the projected total score **0%** (you can't win if you guessed too high).
- The closest valid guess scores **99%**.
- All other valid guesses are scaled linearly between 0% and 99% based on their distance from the projection.

## Example Output

```
Predicted year-end total: 312
Likely winner ranking:
 1. Dylan :  99% ........ guess: 267
 2. Shelja:  88% ........ guess: 255
 3. Pat   :  71% ........ guess: 167
```
