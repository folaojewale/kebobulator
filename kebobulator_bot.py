import asyncio
import os
from datetime import date

import discord

from kebobulator import (
    DEFAULT_START_OF_YEAR,
    build_discord_message,
    fetch_channel_image_count,
    load_dotenv,
    possible_winner,
    send_to_discord,
    validate_bot_token_format,
)


def message_has_image(message: discord.Message) -> bool:
    image_extensions = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg")

    for attachment in message.attachments:
        content_type = (attachment.content_type or "").lower()
        filename = (attachment.filename or "").lower()
        if content_type.startswith("image/") or filename.endswith(image_extensions):
            return True

    for embed in message.embeds:
        embed_type = (embed.type or "").lower()
        if embed_type in {"image", "gifv"}:
            return True
        if embed.image and embed.image.url:
            return True

    return False


class KebobulatorBot(discord.Client):
    def __init__(self, channel_id: int, webhook_url: str, bot_token: str):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        super().__init__(intents=intents)

        self.channel_id = channel_id
        self.webhook_url = webhook_url
        self.bot_token = bot_token
        self._processing_lock = asyncio.Lock()

    async def on_ready(self):
        print(f"Logged in as {self.user} (channel watch: {self.channel_id})")

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != self.channel_id:
            return
        if not message_has_image(message):
            return

        async with self._processing_lock:
            try:
                await self._run_prediction_and_post()
            except Exception as error:
                print(f"Failed to process new image event: {error}")

    async def _run_prediction_and_post(self):
        as_of = date.today()

        eaten = await asyncio.to_thread(
            fetch_channel_image_count,
            str(self.channel_id),
            self.bot_token,
            DEFAULT_START_OF_YEAR,
            as_of,
        )

        predicted_total, winners = await asyncio.to_thread(
            possible_winner,
            eaten,
            as_of,
        )

        message_text = build_discord_message(predicted_total, winners, as_of)
        sent = await asyncio.to_thread(send_to_discord, self.webhook_url, message_text)

        if sent:
            print(
                f"Posted update after new image. Current image count since "
                f"{DEFAULT_START_OF_YEAR.isoformat()}: {eaten}"
            )


def main():
    load_dotenv()

    bot_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    channel_id_text = os.getenv("DISCORD_CHANNEL_ID", "").strip()
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

    if not bot_token or not channel_id_text or not webhook_url:
        raise ValueError(
            "Set DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, and DISCORD_WEBHOOK_URL in .env."
        )

    if not validate_bot_token_format(bot_token):
        raise ValueError(
            "DISCORD_BOT_TOKEN format looks invalid. Use the token from Discord Developer Portal > Bot."
        )

    try:
        channel_id = int(channel_id_text)
    except ValueError as error:
        raise ValueError("DISCORD_CHANNEL_ID must be a numeric channel ID.") from error

    bot = KebobulatorBot(channel_id=channel_id, webhook_url=webhook_url, bot_token=bot_token)
    bot.run(bot_token)


if __name__ == "__main__":
    main()
