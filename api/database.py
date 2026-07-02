"""
Database connection manager with connection pooling support.
"""

import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("medical_warehouse.api")


class DatabaseConnection:
    """Database connection manager with connection pooling support."""

    def __init__(self):
        self.connection = None

    def connect(self):
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", 5433)),
                database=os.getenv("DB_NAME", "medical_warehouse"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "password"),
            )
            logger.info("✓ Database connection established")
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {str(e)}", exc_info=True)
            return False

    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")

    def execute_query(self, query: str, params: tuple = None) -> list:
        """Execute SELECT query and return results."""
        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params or ())
            results = cursor.fetchall()
            cursor.close()
            return results
        except Exception as e:
            logger.error(f"Query execution failed: {str(e)}", exc_info=True)
            raise


db = DatabaseConnection()
