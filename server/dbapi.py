from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from utils import text_snippet
from config import DB_FILE, PAGEDIR, PREVIEWLIMIT, PREVIEWWORD, LOGINJSON, TEACHERJSON
import time
import json
from pathlib import Path
import uuid as uuid
import sqlite3
import re
from flask import g as flask_g
import hashlib
from functools import lru_cache

db = None

GLOBALSCHEMA = """
CREATE TABLE IF NOT EXISTS reads (
    uuid TEXT PRIMARY KEY,
    title TEXT,
    creator TEXT,
    created TEXT,
    type TEXT,
    preview TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT,
    password TEXT,
    role TEXT
);

CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    subject TEXT,
    bio TEXT,
    role TEXT,
    mtime REAL
);
"""

class DButils: # complete
    def __init__(self, dbFile):
        self.dbFile = str(dbFile)
        
    @staticmethod
    def connect() -> sqlite3.Connection:
        """Per-request SQLite connection using flask.g"""
        if not hasattr(flask_g, "_db") or flask_g._db is None:
            conn = sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            flask_g._db = conn
        return flask_g._db

    @staticmethod
    def init_db():
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.row_factory = sqlite3.Row
                conn.executescript(GLOBALSCHEMA)
                conn.commit()
        finally:
            print("DB Initialized")
        
    @staticmethod
    def get_db() -> sqlite3.Connection:
        if db is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        return db

    @staticmethod
    def syncAll():
        steps = [
            ("Initialize DB...  ", DButils.init_db),
            ("Sync users...     ", UserAPI.sync),
            ("Sync teachers...  ", TeacherAPI.sync),
            ("Import reads...   ", ReadsAPI.importFromDir)]
        for i, (label, func) in enumerate(steps, 1):
            print(f"[{i}/{len(steps)}] {label}", end='', flush=True)
            func()
        print("Synchronized all data sources.")
        return {"status": "success"}

    @staticmethod
    def close():
        db = getattr(flask_g, "_db", None)
        if db is not None:
            db.close()
            flask_g._db = None

class ReadsAPI: # complete
    @staticmethod
    def add(title: str="No Title", creator: str = "admin", content: str= "No Content.", type_: str = "article") -> str: # unused
        now = datetime.now(timezone.utc)
        uid = str(uuid.uuid4())
        date_path = now.strftime("%Y/%m/%d")
        base = Path(PAGEDIR) / date_path
        base.mkdir(parents=True, exist_ok=True)

        fpath = base / f"{uid}.md"

        md = (
            f"---\n"
            f"date: '{now.strftime('%Y-%m-%d %H:%M:%S')}'\n"
            f"title: {title}\n"
            f"uuid: {uid}\n"
            f"creator: {creator}\n"
            f"type: {type_}\n"
            f"---\n\n"
            f"{content.strip()}\n"
        )

        with open(fpath, "w", encoding="utf-8") as f:
            f.write(md)

        preview = text_snippet(content, 180)
        DButils.init_db()
        connection = DButils.connect()
        connection.execute(
            """
            INSERT INTO reads (uuid, title, creator, created, type, preview, mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [uid, title, creator, now.isoformat(), type_, preview, now.timestamp()],
        )
        connection.commit()

        print( f"Created new read: {title} ({uid})" )
        return uid

    @staticmethod
    def preview(slug: str) -> Optional[Dict[str, Any]]: # unused
        DButils.init_db()
        connection = DButils.connect()
        cursor = connection.execute(
            "SELECT uuid, title, creator, created, type, preview FROM reads WHERE uuid = ?",
            [slug]
        )
        row = cursor.fetchone()
        if row:
            return {
                "uuid": row[0],
                "title": row[1],
                "creator": row[2],
                "created": row[3],
                "type": row[4],
                "preview": row[5]
            }
        return None

    @staticmethod
    @lru_cache(maxsize=512)
    def pageList(offset: int = 0, limit: int = PREVIEWLIMIT, query: str = "") -> Dict[str, Any]: # complete
        DButils.init_db()
        connection = DButils.connect()
        
        sql = "SELECT * FROM reads"
        params: List[Any] = []

        if query:
            sql += " WHERE title LIKE ? OR creator LIKE ?"
            qparam = f"%{query}%"
            params.extend([qparam, qparam])
        
        sql_count = "SELECT COUNT(*) FROM reads"
        if query:
            sql_count += " WHERE title LIKE ? OR creator LIKE ?"

        # total count
        cursor = connection.execute(sql_count, params)
        total = cursor.fetchone()[0]

        sql += " ORDER BY created DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = connection.execute(sql, params)
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

        connection = DButils.connect()
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

            connection.execute(
                """
                INSERT OR REPLACE INTO reads
                (uuid, title, creator, created, type, preview)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [meta["uuid"], meta["title"], meta["creator"], meta["date"], meta["type"], preview],
            )
        connection.commit()
        print(f"Imported: {connection.total_changes}")
        return True

    @staticmethod
    @lru_cache(maxsize=512)

    def read(uuid: str) -> Optional[Dict[str, Any]]: # complete
        connection = DButils.connect()
        cursor = connection.execute(
            "SELECT * FROM reads WHERE uuid = ?",
            [uuid]
        )
        connection.close()
        row = cursor.fetchone()
        if row:
            md_path = Path(PAGEDIR) / datetime.fromisoformat(row['created'].replace("\'","")).strftime("%Y/%m/%d") / f"{uuid}.md"
            if md_path.exists():
                content = md_path.read_text(encoding="utf-8")
            else:
                content = row.get('preview', '')
            return {**dict(row), "content": content}
        return None

    @staticmethod
    def clearCache() -> None: # unused
        if hasattr(ReadsAPI, '_cache'):
            ReadsAPI._cache.clear() # type: ignore
        print("Cache cleared.")

class UserAPI: # complete
    @staticmethod
    def _hashPassword(password: str) -> str: # complete
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def _loadJSON() -> Dict[str, Dict[str, Any]]: # complete
        if not LOGINJSON.exists():
            return {}
        try:
            with LOGINJSON.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _writeJSON(allUsers: Dict[str, Dict[str, Any]]) -> None: # complete
        LOGINJSON.parent.mkdir(exist_ok=True)
        with LOGINJSON.open("w", encoding="utf-8") as f:
            json.dump(allUsers, f, indent=2)

    @staticmethod
    def add(username: str, password: str, role: str = "user") -> str: # complete
        uid = str(uuid.uuid4())
        hashed = UserAPI._hashPassword(password)

        # DB insert
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT)"
        )
        conn.execute(
            "INSERT INTO users (id, username, password, role) VALUES (?, ?, ?, ?)",
            (uid, username, hashed, role)
        )
        conn.commit()

        # JSON insert
        allUsers = UserAPI._loadJSON()
        allUsers[uid] = {"id": uid, "username": username, "password": hashed, "role": role, "_mtime": time.time()}
        UserAPI._writeJSON(allUsers)

        return uid

    @staticmethod
    def log(username: str, password: str) -> bool: # complete
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.execute("SELECT password FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        return bool(row and UserAPI._hashPassword(password) == row[0])

    @staticmethod
    def get(userId: str) -> Optional[Dict[str, Any]]: # complete
        allUsers = UserAPI._loadJSON()
        return allUsers.get(userId)

    @staticmethod
    def list(offset: int = 0, limit: int = 10) -> List[Dict[str, Any]]: # complete
        allUsers = list(UserAPI._loadJSON().values())
        return allUsers[offset:offset + limit]

    @staticmethod
    def update(userId: str, username = None, password= None, role = None) -> bool: # complete
        conn = sqlite3.connect(DB_FILE)
        fields, values = [], []

        if username:
            fields.append("username=?")
            values.append(username)
        if password:
            fields.append("password=?")
            values.append(UserAPI._hashPassword(password))
        if role:
            fields.append("role=?")
            values.append(role)
        if not fields:
            return False

        values.append(userId)
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()

        # Update JSON
        allUsers = UserAPI._loadJSON()
        if userId in allUsers:
            if username:
                allUsers[userId]["username"] = username
            if password:
                allUsers[userId]["password"] = UserAPI._hashPassword(password)
            if role:
                allUsers[userId]["role"] = role
            allUsers[userId]["_mtime"] = time.time()
            UserAPI._writeJSON(allUsers)

        return True

    @staticmethod
    def delete(userId: str) -> bool: # complete
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.execute("DELETE FROM users WHERE id = ?", (userId,))
        conn.commit()

        # Remove from JSON
        allUsers = UserAPI._loadJSON()
        if userId in allUsers:
            allUsers.pop(userId)
            UserAPI._writeJSON(allUsers)

        return cursor.rowcount > 0

    @staticmethod
    def search(query: str, offset: int = 0, limit: int = 10) -> List[Dict[str, Any]]: # complete
        qparam = query.lower()
        allUsers = [u for u in UserAPI._loadJSON().values() if qparam in u["username"].lower() or qparam in u["role"].lower()]
        return allUsers[offset:offset + limit]

    @staticmethod
    def exists(username: str) -> bool: # complete
        allUsers = UserAPI._loadJSON()
        return any(u["username"] == username for u in allUsers.values())

    @staticmethod
    def sync(): # complete
        """
        Synchronize DB and JSON.
        Updates older data with newer data; does not delete anything.
        """
        allUsersJSON = UserAPI._loadJSON()

        # Load DB users
        conn = sqlite3.connect(DB_FILE)
        conn.execute("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT)")
        cursor = conn.execute("SELECT id, username, password, role, rowid FROM users")
        dbUsers = {row[0]: {"id": row[0], "username": row[1], "password": row[2], "role": row[3], "db_rowid": row[4]} for row in cursor.fetchall()}

        # JSON -> DB
        for uid, jData in allUsersJSON.items():
            dbData = dbUsers.get(uid)
            jsonTime = jData.get("_mtime", 0)
            dbTime = dbData.get("db_rowid", 0) if dbData else 0
            if not dbData:
                conn = sqlite3.connect(DB_FILE)
                conn.execute(
                    "INSERT INTO users (id, username, password, role) VALUES (?, ?, ?, ?)",
                    (uid, jData["username"], jData["password"], jData["role"])
                )
                conn.commit()
            elif jsonTime > dbTime:
                conn = sqlite3.connect(DB_FILE)
                conn.execute(
                    "UPDATE users SET username=?, password=?, role=? WHERE id=?",
                    (jData["username"], jData["password"], jData["role"], uid)
                )
                conn.commit()

        # DB -> JSON
        for uid, dbData in dbUsers.items():
            jData = allUsersJSON.get(uid)
            dbTime = time.time()
            jsonTime = jData.get("_mtime", 0) if jData else 0
            if not jData or dbTime > jsonTime:
                allUsersJSON[uid] = {"id": dbData["id"], "username": dbData["username"], "password": dbData["password"], "role": dbData["role"], "_mtime": time.time()}
        
        print(f"Imported: {conn.total_changes}")
        UserAPI._writeJSON(allUsersJSON)

class TeacherAPI: # complete
    @staticmethod
    def _load_json() -> Dict[str, Dict[str, Any]]: # complete
        if not TEACHERJSON.exists():
            return {}
        try:
            with TEACHERJSON.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    @staticmethod
    def _write_json(all_teachers: Dict[str, Dict[str, Any]]) -> None: # complete
        TEACHERJSON.parent.mkdir(parents=True, exist_ok=True)
        with TEACHERJSON.open("w", encoding="utf-8") as f:
            json.dump(all_teachers, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _preview_text(text: Optional[str], words: int = PREVIEWWORD) -> str: # complete
        if not text:
            return ""
        parts = text.strip().split()
        return " ".join(parts[:words]) + ("…" if len(parts) > words else "")

    @staticmethod
    def add(name: str, subject: str = "", bio: str = "", role: str = "teacher") -> str: # complete
        tid = str(uuid.uuid4())
        mtime = time.time()
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            "INSERT INTO teachers (id, name, subject, bio, role, mtime) VALUES (?, ?, ?, ?, ?, ?)",
            (tid, name, subject, bio, role, mtime),
        )
        conn.commit()
        
        all_teachers = TeacherAPI._load_json()
        all_teachers[tid] = {
            "id": tid,
            "name": name,
            "subject": subject,
            "bio": bio,
            "role": role,
            "_mtime": mtime,
        }
        TeacherAPI._write_json(all_teachers)

        return tid

    @staticmethod
    def get(teacherId: str) -> Optional[Dict[str, Any]]: # complete
        all_teachers = TeacherAPI._load_json()
        t = all_teachers.get(teacherId)
        if t:
            return t


        conn = sqlite3.connect(DB_FILE)
        cursor = conn.execute(
            "SELECT id, name, subject, bio, role, mtime FROM teachers WHERE id = ?",
            (teacherId,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "subject": row[2],
                "bio": row[3],
                "role": row[4],
                "_mtime": row[5] or time.time(),
            }
        return None

    @staticmethod
    def list(offset: int = 0, limit: int = 10) -> List[Dict[str, Any]]: # complete
        all_teachers = list(TeacherAPI._load_json().values())
        all_teachers.sort(key=lambda x: x.get("_mtime", 0), reverse=True)
        return all_teachers[offset : offset + limit]

    @staticmethod
    def update(teacherId: str, name: Optional[str] = None, subject: Optional[str] = None, bio: Optional[str] = None, role: Optional[str] = None) -> bool: # complete
        if name is None and subject is None and bio is None and role is None:
            return False


        fields = []
        values = []
        if name is not None:
            fields.append("name=?")
            values.append(name)
        if subject is not None:
            fields.append("subject=?")
            values.append(subject)
        if bio is not None:
            fields.append("bio=?")
            values.append(bio)
        if role is not None:
            fields.append("role=?")
            values.append(role)

        mtime = time.time()
        fields.append("mtime=?")
        values.append(mtime)

        values.append(teacherId)
        conn = sqlite3.connect(DB_FILE)
        conn.execute(f"UPDATE teachers SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()

        all_teachers = TeacherAPI._load_json()
        if teacherId in all_teachers:
            if name is not None:
                all_teachers[teacherId]["name"] = name
            if subject is not None:
                all_teachers[teacherId]["subject"] = subject
            if bio is not None:
                all_teachers[teacherId]["bio"] = bio
            if role is not None:
                all_teachers[teacherId]["role"] = role
            all_teachers[teacherId]["_mtime"] = mtime
            TeacherAPI._write_json(all_teachers)
        else:
            row = TeacherAPI.get(teacherId)
            if row:
                row["_mtime"] = mtime
                all_teachers[teacherId] = row
                TeacherAPI._write_json(all_teachers)

        return True

    @staticmethod
    def delete(teacherId: str) -> bool: # complete

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.execute("DELETE FROM teachers WHERE id = ?", (teacherId,))
        conn.commit()

        all_teachers = TeacherAPI._load_json()
        removed = all_teachers.pop(teacherId, None)
        if removed is not None:
            TeacherAPI._write_json(all_teachers)
        return cursor.rowcount > 0

    @staticmethod
    def search(query: str, offset: int = 0, limit: int = 10) -> List[Dict[str, Any]]: # complete
        q = (query or "").strip().lower()
        if not q:
            return TeacherAPI.list(offset=offset, limit=limit)
        results = []
        for t in TeacherAPI._load_json().values():
            if (
                q in (t.get("name") or "").lower()
                or q in (t.get("subject") or "").lower()
                or q in (t.get("bio") or "").lower()
                or q in (t.get("role") or "").lower()
            ):
                results.append(t)
        results.sort(key=lambda x: x.get("_mtime", 0), reverse=True)
        return results[offset : offset + limit]

    @staticmethod
    def exists_by_name(name: str) -> bool: # complete
        if not name:
            return False
        name_l = name.lower()
        for t in TeacherAPI._load_json().values():
            if (t.get("name") or "").lower() == name_l:
                return True
        return False

    @staticmethod
    def preview(teacherId: str) -> Optional[Dict[str, Any]]: # complete
        t = TeacherAPI.get(teacherId)
        if not t:
            return None
        return {
            "id": t["id"],
            "name": t.get("name", ""),
            "subject": t.get("subject", ""),
            "preview": TeacherAPI._preview_text(t.get("bio", ""), PREVIEWWORD),
            "_mtime": t.get("_mtime", 0),
        }

    @staticmethod
    def import_from_json(file_path: Optional[Path] = None) -> int: # complete
        """
        Import teachers from a JSON file (single-file layout described above).
        Returns number of imported/merged records.
        """
        src = Path(file_path) if file_path else TEACHERJSON
        if not src.exists():
            return 0
        try:
            with src.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return 0
        except Exception:
            return 0

        all_main = TeacherAPI._load_json()
        imported = 0

        conn = sqlite3.connect(DB_FILE)
        for tid, rec in data.items():
            if not isinstance(rec, dict):
                continue
            name = rec.get("name", "")
            subject = rec.get("subject", "")
            bio = rec.get("bio", "")
            role = rec.get("role", "teacher")
            mtime = rec.get("_mtime", time.time())

            # upsert DB
            cursor = conn.execute("SELECT 1 FROM teachers WHERE id = ?", (tid,))
            exists = cursor.fetchone() is not None
            if exists:
                conn.execute(
                    "UPDATE teachers SET name=?, subject=?, bio=?, role=?, mtime=? WHERE id=?",
                    (name, subject, bio, role, mtime, tid),
                )
            else:
                conn.execute(
                    "INSERT INTO teachers (id, name, subject, bio, role, mtime) VALUES (?, ?, ?, ?, ?, ?)",
                    (tid, name, subject, bio, role, mtime),
                )
            all_main[tid] = {"id": tid, "name": name, "subject": subject, "bio": bio, "role": role, "_mtime": mtime}
            imported += 1
        conn.commit()
        TeacherAPI._write_json(all_main)
        return imported

    @staticmethod
    def export_to_json(file_path: Optional[Path] = None) -> Path: # complete
        dst = Path(file_path) if file_path else TEACHERJSON.parent / "teachers_export.json"
        all_teachers = TeacherAPI._load_json()
        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("w", encoding="utf-8") as f:
            json.dump(all_teachers, f, indent=2, ensure_ascii=False)
        return dst

    @staticmethod
    def sync() -> None: # complete

        all_json = TeacherAPI._load_json()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.execute("SELECT id, name, subject, bio, role, mtime FROM teachers")
        db_map: Dict[str, Dict[str, Any]] = {}
        for row in cursor.fetchall():
            db_map[row[0]] = {
                "id": row[0],
                "name": row[1],
                "subject": row[2],
                "bio": row[3],
                "role": row[4],
                "mtime": row[5] or 0,
            }

        conn = sqlite3.connect(DB_FILE)
        for tid, jrec in all_json.items():
            j_mtime = float(jrec.get("_mtime", 0))
            dbrec = db_map.get(tid)
            if not dbrec:
                conn.execute(
                    "INSERT OR IGNORE INTO teachers (id, name, subject, bio, role, mtime) VALUES (?, ?, ?, ?, ?, ?)",
                    (tid, jrec.get("name", ""), jrec.get("subject", ""), jrec.get("bio", ""), jrec.get("role", "teacher"), j_mtime),
                )
            elif j_mtime > (dbrec.get("mtime", 0) or 0):
                conn.execute(
                    "UPDATE teachers SET name=?, subject=?, bio=?, role=?, mtime=? WHERE id=?",
                    (jrec.get("name", ""), jrec.get("subject", ""), jrec.get("bio", ""), jrec.get("role", "teacher"), j_mtime, tid),
                )
        conn.commit()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.execute("SELECT id, name, subject, bio, role, mtime FROM teachers")
        for row in cursor.fetchall():
            tid = row[0]
            db_mtime = float(row[5] or 0)
            jrec = all_json.get(tid)
            if not jrec or db_mtime > float(jrec.get("_mtime", 0)):
                all_json[tid] = {
                    "id": tid,
                    "name": row[1],
                    "subject": row[2],
                    "bio": row[3],
                    "role": row[4],
                    "_mtime": db_mtime if db_mtime > 0 else time.time(),
                }
        print(f"Imported: {conn.total_changes}")
        TeacherAPI._write_json(all_json)