"""
Task 2: Load YOLO Image Detection Results

Loads image_detections.csv into PostgreSQL processed schema.

Pipeline:
YOLO -> CSV -> PostgreSQL -> dbt staging -> marts
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from dotenv import load_dotenv

from src.logging_config import logger_loader

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5433))
DB_NAME = os.getenv("DB_NAME", "medical_warehouse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

CSV_FILE = Path("data/processed/image_detections.csv")


class ImageDetectionLoader:

    def __init__(self):

        self.conn = None
        self.cursor = None

        self.records_loaded = 0
        self.duplicates_skipped = 0
        self.errors = []

    # Connection

    def connect(self):

        try:

            logger_loader.info(
                f"Connecting to PostgreSQL {DB_HOST}:{DB_PORT}/{DB_NAME}"
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

            logger_loader.info("✓ Connected")

            return True

        except Exception as e:

            logger_loader.error(e, exc_info=True)
            return False

    # Schema

    def create_schema(self):

        self.cursor.execute("""
            CREATE SCHEMA IF NOT EXISTS processed;
            """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed.image_detections(

                id SERIAL PRIMARY KEY,

                message_id INTEGER NOT NULL,

                image_path TEXT NOT NULL,

                channel_name VARCHAR(255),

                image_category VARCHAR(100),

                detection_count INTEGER DEFAULT 0,

                detected_objects TEXT,

                processed_at TIMESTAMP,

                loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(message_id)

            );
            """)

        indexes = [
            """
            CREATE INDEX IF NOT EXISTS idx_img_message
            ON processed.image_detections(message_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_img_channel
            ON processed.image_detections(channel_name);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_img_category
            ON processed.image_detections(image_category);
            """,
        ]

        for idx in indexes:
            self.cursor.execute(idx)

        self.conn.commit()

        logger_loader.info("✓ processed.image_detections ready")

    # Load CSV

    def load_csv(self):

        if not CSV_FILE.exists():

            raise FileNotFoundError(CSV_FILE)

        logger_loader.info(f"Reading {CSV_FILE}")

        df = pd.read_csv(CSV_FILE)

        logger_loader.info(f"{len(df)} rows found")

        df = df.where(pd.notnull(df), None)

        values = []

        for _, row in df.iterrows():

            values.append(
                (
                    int(row["message_id"]),
                    row["image_path"],
                    row["channel_name"],
                    row["image_category"],
                    int(row["detection_count"]),
                    row["detected_objects"],
                    row["processed_at"],
                )
            )

        insert_sql = """
        INSERT INTO processed.image_detections(

            message_id,

            image_path,

            channel_name,

            image_category,

            detection_count,

            detected_objects,

            processed_at

        )

        VALUES %s

        ON CONFLICT(message_id)

        DO NOTHING;
        """

        execute_values(
            self.cursor,
            insert_sql,
            values,
            page_size=500,
        )

        inserted = self.cursor.rowcount

        self.records_loaded += inserted

        self.duplicates_skipped += len(values) - inserted

        self.conn.commit()

        logger_loader.info(
            f"Inserted {inserted} rows "
            f"(Skipped {self.duplicates_skipped} duplicates)"
        )

    # Validation

    def validate(self):

        self.cursor.execute("""
            SELECT

                COUNT(*) total,

                COUNT(DISTINCT channel_name) channels,

                COUNT(CASE WHEN detection_count>0 THEN 1 END) detected,

                AVG(detection_count) avg_objects

            FROM processed.image_detections;
            """)

        m = self.cursor.fetchone()

        logger_loader.info("=" * 60)
        logger_loader.info("IMAGE DETECTION SUMMARY")
        logger_loader.info("=" * 60)
        logger_loader.info(f"Rows              : {m['total']}")
        logger_loader.info(f"Channels          : {m['channels']}")
        logger_loader.info(f"Detected Images   : {m['detected']}")
        logger_loader.info(f"Average Objects   : {m['avg_objects']:.2f}")
        logger_loader.info("=" * 60)

    # Report

    def save_report(self):

        Path("logs").mkdir(exist_ok=True)

        report = {
            "timestamp": datetime.now().isoformat(),
            "rows_loaded": self.records_loaded,
            "duplicates_skipped": self.duplicates_skipped,
            "errors": self.errors,
        }

        report_file = Path(
            f"logs/image_detection_load_report_" f"{datetime.now():%Y%m%d_%H%M%S}.json"
        )

        with open(report_file, "w") as f:

            json.dump(report, f, indent=4)

        logger_loader.info(f"Report saved -> {report_file}")

    # Run

    def run(self):

        try:

            if not self.connect():
                return False

            self.create_schema()

            self.load_csv()

            self.validate()

            self.save_report()

            logger_loader.info("✓ Image detection loading completed")

            return True

        except Exception as e:

            if self.conn:
                self.conn.rollback()

            logger_loader.error(e, exc_info=True)

            return False

        finally:

            if self.cursor:
                self.cursor.close()

            if self.conn:
                self.conn.close()


def main():

    loader = ImageDetectionLoader()

    success = loader.run()

    return success


if __name__ == "__main__":

    sys.exit(0 if main() else 1)
