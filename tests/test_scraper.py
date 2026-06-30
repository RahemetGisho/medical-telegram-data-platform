import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.scraper import TelegramScraper, ScrapedMessage


@pytest.fixture
def scraper():
    return TelegramScraper()


# normalize channel


def test_normalize_channel_alias(scraper):
    assert scraper._normalize_channel("Doctors online ET") == "@Thequorachannel"


def test_normalize_channel_link(scraper):
    assert (
        scraper._normalize_channel("https://t.me/lobelia4cosmetics")
        == "@lobelia4cosmetics"
    )


def test_normalize_channel_adds_at(scraper):
    assert scraper._normalize_channel("tikvahpharma") == "@tikvahpharma"


# ScrapedMessage


def test_scraped_message_valid():

    msg = ScrapedMessage(
        message_id=1,
        channel_name="abc",
        message_date="2026-06-29",
        message_text="hello",
        has_media=False,
        image_path=None,
        views=10,
        forwards=2,
    )

    assert msg.is_valid()


def test_scraped_message_invalid():

    msg = ScrapedMessage(
        message_id=0,
        channel_name="",
        message_date="",
        message_text=None,
        has_media=False,
        image_path=None,
        views=0,
        forwards=0,
    )

    assert not msg.is_valid()


# get_channel_entity


@pytest.mark.asyncio
async def test_get_channel_entity_success(scraper):

    scraper.client.get_entity = AsyncMock(return_value="entity")

    entity = await scraper._get_channel_entity("tikvahpharma")

    assert entity == "entity"


@pytest.mark.asyncio
async def test_get_channel_entity_failure(scraper):

    scraper.client.get_entity = AsyncMock(side_effect=Exception("failed"))

    entity = await scraper._get_channel_entity("tikvahpharma")

    assert entity is None


# extract message


@pytest.mark.asyncio
async def test_extract_message(scraper):

    scraper._download_media = AsyncMock(return_value=None)

    fake = MagicMock()
    fake.id = 10
    fake.message = "Hello World"
    fake.date = datetime.now(timezone.utc)
    fake.media = None
    fake.views = 15
    fake.forwards = 3
    fake.reactions = None

    result = await scraper._extract_message_data(fake, "channel")

    assert result.message_id == 10
    assert result.message_text == "Hello World"
    assert result.views == 15
    assert result.forwards == 3
    assert result.has_media is False


# authenticate


@pytest.mark.asyncio
async def test_authenticate_success(scraper):

    scraper.client.is_connected = MagicMock(return_value=False)
    scraper.client.connect = AsyncMock()
    scraper.client.start = AsyncMock()

    assert await scraper.authenticate() is True


@pytest.mark.asyncio
async def test_authenticate_failure(scraper):

    scraper.client.is_connected = MagicMock(return_value=False)
    scraper.client.connect = AsyncMock(side_effect=Exception())

    assert await scraper.authenticate() is False


# save_raw_data


@pytest.mark.asyncio
async def test_save_raw_data(tmp_path, scraper):

    from src import scraper as scraper_module

    scraper_module.RAW_DATA_PATH = tmp_path

    msg = ScrapedMessage(
        message_id=1,
        channel_name="tikvahpharma",
        message_date=datetime.now().isoformat(),
        message_text="hello",
        has_media=False,
        image_path=None,
        views=1,
        forwards=1,
    )

    await scraper.save_raw_data([msg], "tikvahpharma")

    files = list(tmp_path.rglob("*.json"))

    assert len(files) == 1


# scrape_channel when channel not found


@pytest.mark.asyncio
async def test_scrape_channel_channel_not_found(scraper):

    scraper._get_channel_entity = AsyncMock(return_value=None)

    result = await scraper.scrape_channel("missing")

    assert result == []
