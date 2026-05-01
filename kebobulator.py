import pandas as pd
import os
import json
import urllib.request
import urllib.error
import urllib.parse
import time
import numpy as np
from datetime import date, datetime

DEFAULT_START_OF_YEAR = date(2026, 1, 1)


def predictor(kebabs_eaten_to_date, as_of_date=None, start_of_year=DEFAULT_START_OF_YEAR):
    """
    Project the full-year total based on the current pace.

    Example: if 50 kebabs are eaten by day 100 of the year,
    projected total = 50 / 100 * 365.
    """
    if as_of_date is None:
        as_of_date = date.today()

    if kebabs_eaten_to_date < 0:
        raise ValueError("kebabs_eaten_to_date must be non-negative")

    if as_of_date < start_of_year:
        raise ValueError("as_of_date must be on or after 2026-01-01")

    start_of_next_year = date(start_of_year.year + 1, 1, 1)
    days_in_year = (start_of_next_year - start_of_year).days
    days_elapsed = (as_of_date - start_of_year).days + 1

    if days_elapsed <= 0:
        raise ValueError("as_of_date must be on or after 2026-01-01")

    projected_total = kebabs_eaten_to_date * (days_in_year / days_elapsed)
    return round(projected_total)


def possible_winner(kebabs_eaten_to_date, as_of_date=None, filename="values.csv"):
    total = predictor(kebabs_eaten_to_date, as_of_date=as_of_date)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, filename)
    df = pd.read_csv(path)

    df["dist"] = (df["value"] - total).abs()

    best_dist = df["dist"].min()
    worst_dist = df["dist"].max()

    MAX_SCORE = 99

    raw_scores = []
    for name, value in zip(df["name"], df["value"]):
        dist = abs(total - value)
        if best_dist == worst_dist:
            outcome = MAX_SCORE
        else:
            outcome = MAX_SCORE * (1 - (dist - best_dist) / (worst_dist - best_dist))
        raw_scores.append((name, outcome, value))

    scores_array = np.array([s[1] for s in raw_scores])
    softmax_scores = np.exp(scores_array) / np.sum(np.exp(scores_array)) * 100

    predicted_values = [
        (name, round(softmax_score), value)
        for (name, _, value), softmax_score in zip(raw_scores, softmax_scores)
    ]
    predicted_values.sort(key=lambda x:[1], reverse=True)
    return total, predicted_values


def parse_optional_date(date_text):
    if not date_text:
        return date.today()
    return datetime.strptime(date_text, "%Y-%m-%d").date()


def validate_bot_token_format(bot_token):
    # Discord bot tokens are typically three base64-like parts separated by dots.
    return bot_token.count(".") == 2


def parse_discord_timestamp(timestamp):
    # Discord timestamp example: 2026-03-07T10:15:30.123000+00:00 or ...Z
    normalized = timestamp.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _is_image_attachment(attachment):
    content_type = (attachment.get("content_type") or "").lower()
    filename = (attachment.get("filename") or "").lower()

    if content_type.startswith("image/"):
        return True

    image_extensions = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg")
    return filename.endswith(image_extensions)


def _message_has_image(message):
    attachments = message.get("attachments", [])
    if any(_is_image_attachment(attachment) for attachment in attachments):
        return True

    embeds = message.get("embeds", [])
    for embed in embeds:
        embed_type = (embed.get("type") or "").lower()
        if embed_type in {"image", "gifv"}:
            return True
        if embed.get("image"):
            return True

    return False


def fetch_channel_image_count(channel_id, bot_token, start_date, end_date):
    """Count image posts in a Discord channel from start_date to end_date (inclusive)."""
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Accept": "application/json",
        "User-Agent": "kebobulator/1.0",
    }

    before_message_id = None
    image_count = 0

    while True:
        query = {"limit": 100}
        if before_message_id:
            query["before"] = before_message_id

        url = (
            f"https://discord.com/api/v10/channels/{channel_id}/messages?"
            f"{urllib.parse.urlencode(query)}"
        )

        request = urllib.request.Request(url, headers=headers, method="GET")
        for attempt in range(1, 4):
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    messages = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as error:
                try:
                    error_body = error.read().decode("utf-8", errors="replace")
                    parsed = json.loads(error_body)
                    discord_message = parsed.get("message", error_body)
                except Exception:
                    discord_message = "<unable to parse Discord error response>"

                is_transient = (
                    error.code in {500, 502, 503, 504}
                    or str(discord_message).strip().lower() == "internal network error"
                )

                if is_transient and attempt < 3:
                    time.sleep(1.2 * attempt)
                    continue

                if error.code == 401:
                    raise ValueError(
                        f"Discord API 401 Unauthorized. Check DISCORD_BOT_TOKEN. Details: {discord_message}"
                    ) from None

                if error.code == 403:
                    raise ValueError(
                        "Discord API 403 Forbidden while reading channel messages. "
                        "Ensure the bot is in the server and has 'View Channel' + 'Read Message History' "
                        f"for channel {channel_id}. Details: {discord_message}"
                    ) from None

                if error.code == 404:
                    raise ValueError(
                        f"Discord API 404 Not Found. Check DISCORD_CHANNEL_ID ({channel_id}) and bot access. "
                        f"Details: {discord_message}"
                    ) from None

                raise ValueError(
                    f"Discord API HTTP {error.code} {error.reason}. Details: {discord_message}"
                ) from None
            except urllib.error.URLError as error:
                if attempt < 3:
                    time.sleep(1.2 * attempt)
                    continue
                raise ValueError(f"Network error while contacting Discord API: {error}") from None

        if not messages:
            break

        stop_paging = False
        for message in messages:
            created_at = parse_discord_timestamp(message["timestamp"]).date()

            if created_at < start_date:
                stop_paging = True
                break

            if created_at <= end_date and _message_has_image(message):
                image_count += 1

        if stop_paging:
            break

        before_message_id = messages[-1]["id"]

    return image_count


def format_winners_pretty(winners):
    rank_width = len(str(len(winners))) if winners else 1
    visible_prefixes = [
        f"{idx:>{rank_width}} {name} : {score:>3}%"
        for idx, (name, score, _) in enumerate(winners, start=1)
    ]
    max_prefix_len = max((len(prefix) for prefix in visible_prefixes), default=0)

    lines = []
    for idx, (name, score, guess) in enumerate(winners, start=1):
        visible_prefix = f"{idx:>{rank_width}} {name} : {score:>3}%"
        leader_count = max(4, (max_prefix_len - len(visible_prefix)) + 8)
        lines.append(f"**{idx:>{rank_width}}**. {name} : {score:>3}%")
        #{'.' * leader_count} guess: {guess} hiding their guesses 
    return lines


def build_discord_message(predicted_total, winners, as_of_date, image_count):
    ranking_lines = format_winners_pretty(winners)

    lines = [
        f"**Kebab Prediction Update: {as_of_date.isoformat()}**",
        f"**Image count to date: {image_count}**",
        f"**Predicted year-end total: {predicted_total}**",
        "**Prediction Rankings:**",
        "\n".join(ranking_lines),
    ]

    return "\n".join(lines)


def send_to_discord(webhook_url, message):
    payload = json.dumps({"content": message}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10):
            return True
    except urllib.error.HTTPError as error:
        try:
            error_body = error.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = "<unable to read error body>"
        print(f"Failed to send Discord message: HTTP {error.code} {error.reason}")
        print(f"Discord API response: {error_body}")
        return False
    except urllib.error.URLError as error:
        print(f"Failed to send Discord message: {error}")
        return False


def load_dotenv(dotenv_path=".env"):
    """Load KEY=VALUE pairs from a .env file into process env if not already set."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, dotenv_path)

    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


if __name__ == "__main__":
    load_dotenv()

    try:
        date_text = input("As-of date (YYYY-MM-DD, press Enter for today): ").strip()
        eaten_text = input(
            "How many kebabs has the person eaten so far this year? "
            "(press Enter to auto-count images from Discord): "
        ).strip()

        as_of = parse_optional_date(date_text)

        if eaten_text:
            eaten = int(eaten_text)
        else:
            bot_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
            channel_id = os.getenv("DISCORD_CHANNEL_ID", "").strip()

            if not bot_token or not channel_id:
                raise ValueError(
                    "Set DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID in .env to auto-count channel images."
                )

            if not validate_bot_token_format(bot_token):
                raise ValueError(
                    "DISCORD_BOT_TOKEN format looks invalid. Use the bot token from Discord Developer Portal > Application > Bot > Reset/View Token."
                )

            try:
                eaten = fetch_channel_image_count(
                    channel_id=channel_id,
                    bot_token=bot_token,
                    start_date=DEFAULT_START_OF_YEAR,
                    end_date=as_of,
                )
                print(f"Auto-counted images in channel since {DEFAULT_START_OF_YEAR.isoformat()}: {eaten}")
            except ValueError as error:
                print(f"Warning: {error}")
                fallback_text = input("Enter kebab count manually to continue: ").strip()
                if not fallback_text:
                    raise ValueError("Auto-count failed and no manual count was provided.")
                eaten = int(fallback_text)
    except ValueError as error:
        print(f"Error: {error}")
        raise SystemExit(1)

    predicted_total, winners = possible_winner(eaten, as_of_date=as_of)
    ranking_lines = format_winners_pretty(winners)

    print(f"Predicted year-end total: {predicted_total}")
    print("Likely winner ranking:")

    for row in ranking_lines:
        print(row)

    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if webhook_url:
        message = build_discord_message(predicted_total, winners, as_of, eaten)
        sent = send_to_discord(webhook_url, message)
        if sent:
            print("\nPosted prediction to Discord.")
    else:
        print("\nSet DISCORD_WEBHOOK_URL to post this prediction to Discord.")