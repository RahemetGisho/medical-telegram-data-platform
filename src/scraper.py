import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

from telethon.errors import FloodWaitError, RPCError
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

from src.logging_config import logger_scraper

# Load environment variables
load_dotenv()

# Configuration
API_ID = int(os.getenv("TELEGRAM_API_ID", 0))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
PHONE_NUMBER = os.getenv("TELEGRAM_PHONE_NUMBER", "")

CHANNELS = [
    c.strip() for c in os.getenv("TELEGRAM_CHANNELS", "").split(",") if c.strip()
]

RAW_DATA_PATH = Path(os.getenv("RAW_DATA_PATH", "data/raw"))
LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))

RATE_LIMIT_DELAY = 1.5
BATCH_SIZE = 100
MAX_RETRIES = 3


class ChannelType(Enum):
    PHARMACEUTICAL = "Pharmaceutical"
    COSMETICS = "Cosmetics"
    MEDICAL = "Medical"
    OTHER = "Other"


@dataclass
class ScrapedMessage:
    message_id: int
    channel_name: str
    message_date: str
    message_text: Optional[str]
    has_media: bool
    image_path: Optional[str]
    views: int
    forwards: int
    reactions: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def is_valid(self) -> bool:
        return bool(self.message_id and self.channel_name and self.message_date)


class TelegramScraper:

    def __init__(self):
        self.client = TelegramClient(
            "medical_warehouse_session",
            API_ID,
            API_HASH,
            system_version="4.16.30-vxWinx",
            auto_reconnect=True,
            connection_retries=20,
            retry_delay=5,
            timeout=30,
        )

        self.messages_collected = 0
        self.images_downloaded = 0
        self.errors = []

        # username mapping
        self.channel_aliases = {
            "Doctors online ET": "Thequorachannel",
            "Lobelia Cosmetics": "lobelia4cosmetics",
            "Tikvah Pharma": "tikvahpharma",
        }

        self.channel_metadata = {
            "Thequorachannel": ChannelType.MEDICAL,
            "lobelia4cosmetics": ChannelType.COSMETICS,
            "tikvahpharma": ChannelType.PHARMACEUTICAL,
        }

    def _normalize_channel(self, channel_name: str) -> str:
        channel_name = channel_name.strip()

        # convert t.me links
        if "t.me/" in channel_name:
            channel_name = channel_name.split("t.me/")[-1].strip("/")

        # alias mapping
        channel_name = self.channel_aliases.get(channel_name, channel_name)

        # remove spaces
        channel_name = channel_name.replace(" ", "")

        # ensure @
        if not channel_name.startswith("@"):
            channel_name = "@" + channel_name

        return channel_name

    async def authenticate(self) -> bool:
        try:
            logger_scraper.info("Starting Telegram authentication...")
            if not self.client.is_connected():
                await self.client.connect()
            await self.client.start(phone=PHONE_NUMBER)
            logger_scraper.info("✓ Authentication successful")
            return True
        except Exception as e:
            logger_scraper.error(f"✗ Authentication failed: {str(e)}", exc_info=True)
            return False

    async def scrape_channel(
        self, channel_name: str, days_back: int = 7, limit: Optional[int] = None
    ) -> List[ScrapedMessage]:

        logger_scraper.info(f"Starting scrape: {channel_name} (last {days_back} days)")

        messages: List[ScrapedMessage] = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        try:
            entity = await self._get_channel_entity(channel_name)

            if not entity:
                logger_scraper.warning(f"Channel not found: {channel_name}")
                return []

            message_count = 0

            async for message in self.client.iter_messages(
                entity, limit=limit, reverse=False  # newest -> oldest
            ):
                # stop once we pass the cutoff
                if message.date < cutoff_date:
                    logger_scraper.info(
                        f"Reached {days_back}-day limit for {channel_name}"
                    )
                    break

                try:
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                    scraped = await self._extract_message_data(message, channel_name)

                    if scraped and scraped.is_valid():
                        messages.append(scraped)
                        message_count += 1

                        if message_count % 50 == 0:
                            logger_scraper.info(
                                f"Processed {message_count} messages from {channel_name}"
                            )

                except FloodWaitError as e:
                    logger_scraper.warning(f"Flood wait ({e.seconds}s)")
                    await asyncio.sleep(e.seconds)

                except (OSError, TimeoutError, RPCError) as e:
                    logger_scraper.warning(f"Connection lost ({e}). Reconnecting...")
                    try:
                        if self.client.is_connected():
                            await self.client.disconnect()

                        await asyncio.sleep(5)
                        await self.client.connect()

                        if not await self.client.is_user_authorized():
                            await self.client.start(phone=PHONE_NUMBER)

                        logger_scraper.info("Reconnected.")
                    except Exception as reconnect_error:
                        logger_scraper.error(f"Reconnect failed: {reconnect_error}")
                        break

                except asyncio.CancelledError:
                    logger_scraper.warning(
                        "Scraping cancelled by system or user request."
                    )
                    # Don't throw a raw raise here, break cleanly to allow final state storage
                    break

                except Exception as e:
                    logger_scraper.error(
                        f"Message {getattr(message, 'id', None)} failed: {e}"
                    )
                    self.errors.append(
                        {
                            "channel": channel_name,
                            "message_id": getattr(message, "id", None),
                            "error": str(e),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

            self.messages_collected += len(messages)
            logger_scraper.info(
                f"✓ Completed {channel_name}: {len(messages)} messages collected"
            )

        except FloodWaitError as e:
            logger_scraper.warning(f"Flood wait while reading channel ({e.seconds}s)")
            await asyncio.sleep(e.seconds)
        except asyncio.CancelledError:
            logger_scraper.warning("Channel processing interrupted.")
        except Exception as e:
            logger_scraper.error(f"Failed to scrape {channel_name}: {e}", exc_info=True)

        return messages

    async def _get_channel_entity(self, channel_name: str):
        try:
            channel_name = self._normalize_channel(channel_name)
            return await self.client.get_entity(channel_name)
        except Exception as e:
            logger_scraper.warning(
                f"Could not resolve channel {channel_name}: {str(e)}"
            )
            return None

    async def _extract_message_data(
        self, message, channel_name: str
    ) -> Optional[ScrapedMessage]:
        try:
            image_path = None
            has_media = message.media is not None

            if has_media and isinstance(
                message.media, (MessageMediaPhoto, MessageMediaDocument)
            ):
                image_path = await self._download_media(message, channel_name)

            message_text = message.message or ""

            reactions = 0
            if message.reactions and hasattr(message.reactions, "results"):
                reactions = sum(r.count for r in message.reactions.results)

            return ScrapedMessage(
                message_id=message.id,
                channel_name=channel_name,
                message_date=message.date.isoformat(),
                message_text=message_text[:5000],
                has_media=has_media,
                image_path=image_path,
                views=message.views or 0,
                forwards=message.forwards or 0,
                reactions=reactions,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger_scraper.error(f"Error extracting message data: {str(e)}")
            return None

    async def _download_media(self, message, channel_name: str) -> Optional[str]:
        try:
            media_dir = RAW_DATA_PATH / "images" / channel_name.replace("@", "")
            media_dir.mkdir(parents=True, exist_ok=True)

            file_ext = ".jpg"
            if isinstance(message.media, MessageMediaDocument):
                mime = getattr(message.media.document, "mime_type", "")
                if mime == "image/png":
                    file_ext = ".png"
                elif mime == "image/gif":
                    file_ext = ".gif"

            file_path = media_dir / f"{message.id}{file_ext}"

            for attempt in range(MAX_RETRIES):
                try:
                    await self.client.download_media(message, file=str(file_path))
                    self.images_downloaded += 1
                    return str(file_path)
                except FloodWaitError as e:
                    logger_scraper.warning(f"Media flood wait: {e.seconds}s")
                    await asyncio.sleep(e.seconds)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2**attempt)
                    else:
                        raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger_scraper.warning(
                f"Failed to download media for message {getattr(message, 'id', None)}: {str(e)}"
            )
            return None

    async def save_raw_data(self, messages: List[ScrapedMessage], channel_name: str):
        if not messages:
            logger_scraper.warning(f"No messages to save for {channel_name}")
            return

        try:
            messages_by_date = {}
            for msg in messages:
                date = msg.message_date[:10]
                messages_by_date.setdefault(date, []).append(msg)

            for date, day_messages in messages_by_date.items():
                data_dir = RAW_DATA_PATH / "telegram_messages" / date
                data_dir.mkdir(parents=True, exist_ok=True)

                file_path = (
                    data_dir / f"{channel_name.replace('@','').replace(' ','_')}.json"
                )

                output_data = {
                    "metadata": {
                        "channel_name": channel_name,
                        "channel_type": self.channel_metadata.get(
                            channel_name.replace("@", ""), ChannelType.OTHER
                        ).value,
                        "partition_date": date,
                        "collection_date": datetime.now().isoformat(),
                        "message_count": len(day_messages),
                    },
                    "messages": [msg.to_dict() for msg in day_messages],
                }

                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False, indent=2)

                logger_scraper.info(
                    f"Saved {len(day_messages)} messages to {file_path}"
                )
        except Exception as e:
            logger_scraper.error(
                f"Error saving messages for {channel_name}: {str(e)}", exc_info=True
            )

    async def save_error_report(self):
        if not self.errors:
            return

        error_file = (
            LOG_DIR / f"scraping_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        try:
            with open(error_file, "w") as f:
                json.dump(
                    {
                        "summary": {
                            "total_errors": len(self.errors),
                            "timestamp": datetime.now().isoformat(),
                        },
                        "errors": self.errors,
                    },
                    f,
                    indent=2,
                )
            logger_scraper.info(f"Error report saved to {error_file}")
        except Exception as e:
            logger_scraper.error(f"Failed to save error report: {str(e)}")

    async def generate_scraping_summary(self):
        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_messages_collected": self.messages_collected,
            "total_images_downloaded": self.images_downloaded,
            "total_errors": len(self.errors),
            "channels_scraped": CHANNELS,
        }

        summary_file = (
            LOG_DIR
            / f"scraping_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        try:
            with open(summary_file, "w") as f:
                json.dump(summary, f, indent=2)
            logger_scraper.info("✓ SCRAPING SUMMARY DONE")
        except Exception as e:
            logger_scraper.error(f"Failed summary: {str(e)}")

    async def run(self, days_back: int = 7):
        try:
            if not await self.authenticate():
                return False

            for channel in CHANNELS:
                try:
                    messages = await self.scrape_channel(channel, days_back=days_back)
                    if messages:
                        await self.save_raw_data(messages, channel)
                    await asyncio.sleep(2)
                except asyncio.CancelledError:
                    logger_scraper.warning("Execution loop canceled dynamically.")
                    break

            await self.save_error_report()
            await self.generate_scraping_summary()
            return True
        finally:
            await self.client.disconnect()


async def main():
    RAW_DATA_PATH.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if not API_ID or not API_HASH or not PHONE_NUMBER:
        return False

    if not CHANNELS:
        return False

    scraper = TelegramScraper()
    try:
        return await scraper.run(days_back=7)
    except KeyboardInterrupt:
        logger_scraper.info("Scraper closed by keyboard command.")
        return False


if __name__ == "__main__":
    try:
        sys.exit(0 if asyncio.run(main()) else 1)
    except KeyboardInterrupt:
        logger_scraper.info("Exiting execution environment cleanly.")
        sys.exit(1)
