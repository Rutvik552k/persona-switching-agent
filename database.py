"""
Database module for managing users, professions, and conversation history.
Handles PostgreSQL connections and CRUD operations.
"""

import os
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor


class DatabaseManager:
    """Manages all database operations for the persona/profession-switching chatbot."""

    def __init__(self) -> None:
        # Either use a full DATABASE_URL or individual POSTGRES_* env vars.
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            self._dsn = database_url
            self.db_config = None
        else:
            self._dsn = None
            self.db_config = {
                "host": os.getenv("POSTGRES_HOST", "localhost"),
                "port": int(os.getenv("POSTGRES_PORT", "5432")),
                "dbname": os.getenv("POSTGRES_DB", "postgres"),
                "user": os.getenv("POSTGRES_USER", "postgres"),
                "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
            }

        # Create tables on startup (requires PostgreSQL to be running)
        self.initialize_database()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = None
        try:
            if self._dsn:
                conn = psycopg2.connect(self._dsn)
            else:
                conn = psycopg2.connect(**self.db_config)
            yield conn
            conn.commit()
        except psycopg2.OperationalError as e:
            print(
                "[DatabaseManager] Could not connect to PostgreSQL. "
                "Make sure the server is running and DATABASE_URL or POSTGRES_* "
                f"env vars are set correctly. Original error: {e}"
            )
            raise
        except Exception:
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def initialize_database(self) -> None:
        """Create tables if they don't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create users table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id VARCHAR(255) PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Create conversations table (threads are keyed by persona/profession name)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    persona_name VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
                """
            )

            # Table to store profession-specific prompts per user
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS professions (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    profession_name VARCHAR(255) NOT NULL,
                    prompt TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, profession_name),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
                """
            )

            # Create index for faster queries on conversations
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_persona
                ON conversations(user_id, persona_name, timestamp)
                """
            )

            cursor.close()

    def user_exists(self, user_id: str) -> bool:
        """Check if a user exists in the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM users WHERE user_id = %s",
                (user_id,),
            )
            exists = cursor.fetchone() is not None
            cursor.close()
            return exists

    def create_user(self, user_id: str) -> bool:
        """Create a new user in the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (user_id) VALUES (%s)",
                    (user_id,),
                )
                cursor.close()
                return True
        except psycopg2.IntegrityError:
            # User already exists
            return False
        except Exception as e:
            print(f"Error creating user: {e}")
            return False

    def get_user_personas(self, user_id: str) -> List[str]:
        """Get all unique personas/professions for a user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT persona_name
                FROM conversations
                WHERE user_id = %s
                ORDER BY persona_name
                """,
                (user_id,),
            )
            personas = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return personas

    def get_persona_history(self, user_id: str, persona_name: str) -> List[Dict]:
        """Get conversation history for a specific persona/profession."""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """
                SELECT role, message, timestamp
                FROM conversations
                WHERE user_id = %s AND persona_name = %s
                ORDER BY timestamp ASC
                """,
                (user_id, persona_name),
            )
            history = cursor.fetchall()
            cursor.close()
            return [dict(row) for row in history]

    def get_profession_prompt(self, user_id: str, profession_name: str) -> Optional[str]:
        """Get the stored prompt for a given user + profession, if it exists."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT prompt
                FROM professions
                WHERE user_id = %s AND profession_name = %s
                """,
                (user_id, profession_name),
            )
            row = cursor.fetchone()
            cursor.close()
            if row:
                return row[0]
            return None

    def save_profession_prompt(self, user_id: str, profession_name: str, prompt: str) -> bool:
        """Insert or update the prompt for a given user + profession."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO professions (user_id, profession_name, prompt)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, profession_name)
                    DO UPDATE SET prompt = EXCLUDED.prompt
                    """,
                    (user_id, profession_name, prompt),
                )
                cursor.close()
                return True
        except Exception as e:
            print(f"Error saving profession prompt: {e}")
            return False

    def get_all_chat_history(self, user_id: str) -> Dict[str, List[Dict]]:
        """Get all chat history grouped by persona/profession."""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """
                SELECT persona_name, role, message, timestamp
                FROM conversations
                WHERE user_id = %s
                ORDER BY persona_name, timestamp ASC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
            cursor.close()

            # Group by persona/profession
            history_by_persona: Dict[str, List[Dict]] = {}
            for row in rows:
                persona = row["persona_name"]
                if persona not in history_by_persona:
                    history_by_persona[persona] = []
                history_by_persona[persona].append(
                    {
                        "role": row["role"],
                        "message": row["message"],
                        "timestamp": (
                            row["timestamp"].isoformat()
                            if isinstance(row["timestamp"], datetime)
                            else row["timestamp"]
                        ),
                    }
                )

            return history_by_persona

    def save_message(self, user_id: str, persona_name: str, role: str, message: str) -> bool:
        """Save a single message to the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO conversations (user_id, persona_name, role, message)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, persona_name, role, message),
                )
                cursor.close()
                return True
        except Exception as e:
            print(f"Error saving message: {e}")
            return False

    def persona_exists_for_user(self, user_id: str, persona_name: str) -> bool:
        """Check if a persona/profession thread exists for a user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1
                FROM conversations
                WHERE user_id = %s AND persona_name = %s
                LIMIT 1
                """,
                (user_id, persona_name),
            )
            exists = cursor.fetchone() is not None
            cursor.close()
            return exists

    def delete_user_data(self, user_id: str) -> bool:
        """Delete all data for a user (for cleanup/testing)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
                cursor.close()
                return True
        except Exception as e:
            print(f"Error deleting user data: {e}")
            return False


# Singleton instance used by the FastAPI app
db_manager = DatabaseManager()
