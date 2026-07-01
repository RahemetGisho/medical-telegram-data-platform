"""
Task 1 (Load): Data Lake to Raw Database
Loads scraped JSON files into PostgreSQL raw schema.
Implements incremental loading with deduplication.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor, execute_values
from dotenv import load_dotenv
import pandas as pd

from src.logging_config import logger_loader

# Load environment variables
load_dotenv()

# Database configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5433))
DB_NAME = os.getenv("DB_NAME", "medical_warehouse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
RAW_DATA_PATH = Path(os.getenv("RAW_DATA_PATH", "data/raw"))


class DataLakeLoader:
    """
    Production-grade data loader with error handling and validation.
    Implements idempotent loading with duplicate detection.
    """

    def __init__(self):
        """Initialize database connection."""
        self.conn = None
        self.cursor = None
        self.messages_loaded = 0
        self.duplicates_skipped = 0
        self.errors = []

    def connect(self) -> bool:
        """Establish PostgreSQL connection with validation."""
        try:
            logger_loader.info(
                f"Connecting to PostgreSQL: {DB_HOST}:{DB_PORT}/{DB_NAME}"
            )

            self.conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=10,
            )
            self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)

            # Test connection
            self.cursor.execute("SELECT version();")
            version = self.cursor.fetchone()
            logger_loader.info(f"✓ Connected to: {list(version.values())[0][:50]}...")

            return True

        except psycopg2.Error as e:
            logger_loader.error(
                f"✗ Database connection failed: {str(e)}", exc_info=True
            )
            return False

    def create_raw_schema(self) -> bool:
        """Create raw schema if it doesn't exist."""
        try:
            logger_loader.info("Creating raw schema...")

            # Create schema
            self.cursor.execute("CREATE SCHEMA IF NOT EXISTS raw;")

            # Create raw telegram_messages table
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS raw.telegram_messages (
                id SERIAL PRIMARY KEY,
                message_id INTEGER NOT NULL,
                channel_name VARCHAR(255) NOT NULL,
                message_date TIMESTAMP NOT NULL,
                message_text TEXT,
                has_media BOOLEAN DEFAULT FALSE,
                image_path VARCHAR(512),
                views INTEGER DEFAULT 0,
                forwards INTEGER DEFAULT 0,
                reactions INTEGER DEFAULT 0,
                loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                -- Unique constraint to prevent duplicates
                UNIQUE(message_id, channel_name)
            );
            """

            self.cursor.execute(create_table_sql)

            # Create indexes for query performance
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_raw_messages_channel ON raw.telegram_messages(channel_name);",
                "CREATE INDEX IF NOT EXISTS idx_raw_messages_date ON raw.telegram_messages(message_date);",
                "CREATE INDEX IF NOT EXISTS idx_raw_messages_has_media ON raw.telegram_messages(has_media);",
            ]

            for index_sql in indexes:
                self.cursor.execute(index_sql)

            self.conn.commit()
            logger_loader.info("✓ Raw schema created successfully")
            return True

        except psycopg2.Error as e:
            logger_loader.error(f"Error creating raw schema: {str(e)}", exc_info=True)
            self.conn.rollback()
            return False

    def load_json_files(self) -> bool:
        """
        Discover and load all JSON files from data lake.
        Implements incremental loading with error recovery.
        """
        try:
            json_files = list(RAW_DATA_PATH.glob("telegram_messages/*/*.json"))

            if not json_files:
                logger_loader.warning(f"No JSON files found in {RAW_DATA_PATH}")
                return True

            logger_loader.info(f"Found {len(json_files)} JSON files to process")

            # Load files in batches
            for idx, json_file in enumerate(json_files, 1):
                try:
                    self._load_single_file(json_file)
                    logger_loader.info(
                        f"Processed {idx}/{len(json_files)}: {json_file.name}"
                    )

                except Exception as e:
                    logger_loader.error(f"Error loading {json_file}: {str(e)}")
                    self.errors.append(
                        {
                            "file": str(json_file),
                            "error": str(e),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

            self.conn.commit()
            logger_loader.info(
                f"✓ Loaded {self.messages_loaded} messages, skipped {self.duplicates_skipped} duplicates"
            )
            return True

        except Exception as e:
            logger_loader.error(f"Fatal error during loading: {str(e)}", exc_info=True)
            return False

    def _load_single_file(self, json_file: Path):
        """Load a single JSON file into the database."""
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        messages = data.get("messages", [])
        if not messages:
            logger_loader.warning(f"No messages in {json_file}")
            return

        # Prepare batch insert
        values_list = []
        for msg in messages:
            try:
                values_list.append(
                    (
                        msg.get("message_id"),
                        msg.get("channel_name"),
                        msg.get("message_date"),
                        msg.get("message_text"),
                        msg.get("has_media", False),
                        msg.get("image_path"),
                        msg.get("views", 0),
                        msg.get("forwards", 0),
                        msg.get("reactions", 0),
                    )
                )
            except KeyError as e:
                logger_loader.warning(f"Missing field in message: {str(e)}")
                continue

        if not values_list:
            return

        # Batch insert with conflict handling
        insert_sql = """
        INSERT INTO raw.telegram_messages 
        (message_id, channel_name, message_date, message_text, has_media, 
         image_path, views, forwards, reactions)
        VALUES %s
        ON CONFLICT (message_id, channel_name) DO NOTHING;
        """

        try:
            execute_values(self.cursor, insert_sql, values_list, page_size=100)
            rows_inserted = self.cursor.rowcount
            self.messages_loaded += rows_inserted

            # Estimate duplicates (total attempted - inserted)
            self.duplicates_skipped += len(values_list) - rows_inserted

        except psycopg2.Error as e:
            logger_loader.error(f"Error inserting batch: {str(e)}")
            raise

    def validate_loaded_data(self) -> bool:
        """Validate data quality after loading."""
        try:
            logger_loader.info("Validating loaded data...")

            # Get data quality metrics
            self.cursor.execute("""
            SELECT 
                COUNT(*) as total_messages,
                COUNT(DISTINCT channel_name) as unique_channels,
                COUNT(CASE WHEN message_text IS NULL THEN 1 END) as null_messages,
                COUNT(CASE WHEN has_media THEN 1 END) as messages_with_media,
                COUNT(CASE WHEN image_path IS NOT NULL THEN 1 END) as messages_with_images,
                MIN(message_date) as earliest_message,
                MAX(message_date) as latest_message
            FROM raw.telegram_messages;
            """)

            metrics = self.cursor.fetchone()

            logger_loader.info("=" * 60)
            logger_loader.info("DATA QUALITY METRICS")
            logger_loader.info("=" * 60)
            logger_loader.info(f"Total messages: {metrics['total_messages']}")
            logger_loader.info(f"Unique channels: {metrics['unique_channels']}")
            logger_loader.info(f"Null messages: {metrics['null_messages']}")
            logger_loader.info(f"Messages with media: {metrics['messages_with_media']}")
            logger_loader.info(
                f"Messages with images: {metrics['messages_with_images']}"
            )
            logger_loader.info(
                f"Date range: {metrics['earliest_message']} to {metrics['latest_message']}"
            )
            logger_loader.info("=" * 60)

            # Check for anomalies
            if metrics["null_messages"] > metrics["total_messages"] * 0.1:
                logger_loader.warning(
                    f"High null message ratio: {metrics['null_messages'] / metrics['total_messages'] * 100:.1f}%"
                )

            # Get channel summary
            self.cursor.execute("""
            SELECT 
                channel_name,
                COUNT(*) as message_count,
                COUNT(CASE WHEN has_media THEN 1 END) as media_count,
                AVG(views) as avg_views,
                AVG(forwards) as avg_forwards
            FROM raw.telegram_messages
            GROUP BY channel_name
            ORDER BY message_count DESC;
            """)

            channels = self.cursor.fetchall()
            logger_loader.info("Channel Summary:")
            for channel in channels:
                logger_loader.info(
                    f"  {channel['channel_name']}: "
                    f"{channel['message_count']} messages, "
                    f"{channel['media_count']} with media"
                )

            return True

        except Exception as e:
            logger_loader.error(f"Error validating data: {str(e)}", exc_info=True)
            return False

    def save_load_report(self):
        """Generate and save loading report."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "messages_loaded": self.messages_loaded,
            "duplicates_skipped": self.duplicates_skipped,
            "errors": self.errors,
        }

        report_file = (
            Path("logs")
            / f"load_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        try:
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)
            logger_loader.info(f"Load report saved to {report_file}")
        except Exception as e:
            logger_loader.error(f"Failed to save report: {str(e)}")

    def run(self) -> bool:
        """Main execution flow."""
        try:
            # Connect to database
            if not self.connect():
                return False

            # Create schema
            if not self.create_raw_schema():
                return False

            # Load data
            if not self.load_json_files():
                return False

            # Validate
            self.validate_loaded_data()

            # Save report
            self.save_load_report()

            logger_loader.info("✓ Data loading completed successfully")
            return True

        finally:
            self.disconnect()

    def disconnect(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            logger_loader.info("Database connection closed")


def main():
    """Entry point for data loader."""
    Path("logs").mkdir(exist_ok=True)

    logger_loader.info("Starting Data Lake Loader")
    logger_loader.info(f"Raw data path: {RAW_DATA_PATH}")

    # Validate raw data exists
    if not RAW_DATA_PATH.exists():
        logger_loader.error(f"Raw data path does not exist: {RAW_DATA_PATH}")
        return False

    loader = DataLakeLoader()
    success = loader.run()

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
