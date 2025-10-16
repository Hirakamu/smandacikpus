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
    preview TEXT
);
"""

class DButils:
    @staticmethod
    def connect() -> sqlite3.Connection:
        """Per-request SQLite connection using flask.g (kept for request-scoped usage)."""
        if not hasattr(flask_g, "_db") or flask_g._db is None:
            conn = sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            flask_g._db = conn
        return flask_g._db

    @staticmethod
    def close():
        db = getattr(flask_g, "_db", None)
        if db is not None:
            db.close()
            flask_g._db = None

    @staticmethod
    @contextmanager
    def connection():
        """Context manager that opens a short-lived connection and closes it on exit.
           Use this for background tasks and per-operation DB access.
        """
        conn = sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES, timeout=30)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            yield conn
        finally:
            conn.close()

    @staticmethod
    def init_db():
        # safe one-shot init using a short-lived connection
        with DButils.connection() as conn:
            conn.executescript(GLOBALSCHEMA)
            conn.commit()
        print("DB Initialized")

    @staticmethod
    def syncAll():
        steps = [
            ("Initialize DB...  ", DButils.init_db),
            ("Import reads...   ", ReadsAPI.importFromDir),
        ]
        for i, (label, func) in enumerate(steps, 1):
            print(f"[{i}/{len(steps)}] {label}", end='', flush=True)
            func()
        print("Synchronized all data sources.")
        return {"status": "success"}


class ReadsAPI:
    @staticmethod
    @lru_cache(maxsize=512)
    def pageList(offset: int = 0, limit: int = PREVIEWLIMIT, query: str = "") -> Dict[str, Any]:
        # open/close connection per operation
        where = ""
        params_select: List[Any] = []
        params_count: List[Any] = []

        if query:
            where = " WHERE title LIKE ? OR creator LIKE ?"
            qparam = f"%{query}%"
            params_select.extend([qparam, qparam])
            params_count.extend([qparam, qparam])

        sql_count = f"SELECT COUNT(*) FROM reads{where}"
        sql = f"SELECT * FROM reads{where} ORDER BY created DESC LIMIT ? OFFSET ?"

        with DButils.connection() as conn:
            # total count
            cursor = conn.execute(sql_count, params_count)
            total = cursor.fetchone()[0]

            # fetch items (use fresh params list to avoid mutation issues)
            params = list(params_select) + [limit, offset]
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

            return {
                "items": [dict(row) for row in rows],
                "total": total
            }

    @staticmethod
    def importFromDir() -> bool:
        dirPath = Path(PAGEDIR)
        if not dirPath.exists():
            print("[Import] Directory does not exist:", dirPath)
            return False

        fmRegex = re.compile(r"^---\s*(.*?)---\s*(.*)$", re.DOTALL)

        # use a short-lived connection for bulk import
        with DButils.connection() as conn:
            for file in dirPath.rglob("*.md"):
                text = file.read_text(encoding="utf-8")
                meta = {"uuid": file.stem, "title": file.stem, "creator": "imported", "type": "article", "date": datetime.now(timezone.utc).isoformat()}

                m = fmRegex.match(text)
                body = text
                if m:
                    front, body = m.groups()
                    for line in front.splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            meta[k.strip()] = v.strip()

                preview = text_snippet(body, PREVIEWWORD)

                conn.execute(
                    """
                    INSERT OR REPLACE INTO reads
                    (uuid, title, creator, created, type, preview)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [meta["uuid"], meta["title"], meta["creator"], meta["date"], meta["type"], preview],
                )
            conn.commit()
            print(f"Imported: {conn.total_changes}")

        # clear cached results to reflect newly imported data
        ReadsAPI.clearCache()
        return True

    @staticmethod
    @lru_cache(maxsize=512)
    def read(uuid: str) -> Optional[Dict[str, Any]]:
        with DButils.connection() as conn:
            cursor = conn.execute("SELECT * FROM reads WHERE uuid = ?", [uuid])
            row = cursor.fetchone()
            if not row:
                return None
            row = dict(row)
            created_iso = row["created"].replace("'", "")
            md_path = (Path(PAGEDIR)/datetime.fromisoformat(created_iso).strftime("%Y/%m/%d")/f"{uuid}.md")

            if md_path.exists():
                text = md_path.read_text(encoding="utf-8")
                # strip YAML front-matter
                m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
                if m:
                    _, content = m.groups()
                else:
                    content = text.strip()
            else:
                content = row["preview"]

            del row["preview"]

            return {**dict(row), "content": content.strip()}


    @staticmethod
    def clearCache() -> None:
        # clear lru_cache wrappers if present
        try:
            ReadsAPI.pageList.cache_clear()
            ReadsAPI.read.cache_clear()
        except Exception:
            pass
        print("Cache cleared.")
