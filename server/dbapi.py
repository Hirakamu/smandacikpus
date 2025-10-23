from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from utils import text_snippet
from config import DB_FILE, PAGEDIR, PREVIEWLIMIT, PREVIEWWORD
from pathlib import Path
import uuid as uuid
import sqlite3
import re
from flask import g as flask_g
from functools import lru_cache
from contextlib import contextmanager

GLOBALSCHEMA = """
CREATE TABLE IF NOT EXISTS reads (
    uuid TEXT PRIMARY KEY,
    title TEXT,
    creator TEXT,
    created TEXT,
    type TEXT,
    preview TEXT,
    path TEXT NOT NULL
);
"""

class DButils:
    @staticmethod
    @contextmanager
    def connect():
        """Per-request SQLite connection using flask.g (kept for request-scoped usage)."""
        if not flask_g.get("_db") or flask_g._db is None:
            conn = sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            flask_g._db = conn
        try:
            yield flask_g._db
        finally:
            DButils.close()

    @staticmethod
    def close():
        db = flask_g.get("_db", None)
        if db is not None:
            db.close()
            flask_g._db = None

    @staticmethod
    def init_db():
        # safe one-shot init using a short-lived connection
        with DButils.connect() as conn:
            conn.executescript(GLOBALSCHEMA)
            conn.commit()
        DButils.close()

