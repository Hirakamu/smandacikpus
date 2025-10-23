"""
datacontroller.py

Flask-friendly content versioning for markdown pages using hybrid diffs.

Storage layout (under config.PAGEDIR):
- Canonical file for app consumption:
  PAGEDIR/YYYY/MM/DD/<uuid>.md  (with minimal YAML front-matter)

- Per-page working directory for versioning (hybrid diffs):
  PAGEDIR/YYYY/MM/DD/<uuid>/
    - base.md
    - latest.md (rebuilt from base + diffs)
    - diffs/<NNN>.diff   (difflib.ndiff)
    - diffs/<NNN>.json   (diff metadata)
    - meta.json          (page metadata)

Public API (importable in Flask code):
- page_dir_for(date_iso, uuid) -> Path
- canonical_md_path(date_iso, uuid) -> Path
- init_page(date_iso, title, author, base_text, id_=None) -> str (uuid)
- commit_diff(date_iso, id_, new_text, author, message) -> str (diff filename)
- rebuild_latest(date_iso, id_) -> Path (latest.md)
- view_version(date_iso, id_, index=None) -> str (text)
- list_diffs(date_iso, id_) -> list[(filename, metadata)]
- get_latest_text(date_iso, id_) -> str

The module also has a small CLI for maintenance.
"""

from __future__ import annotations
import json
import uuid as uuidlib
import hashlib
import difflib
import argparse
import os
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from config import PAGEDIR, DB_FILE, PREVIEWWORD

# --------------------------- utils -----------------------------------------

def now_iso() -> str:
    return datetime.now().astimezone().isoformat()

def sha256_of_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def zero_pad(n: int, width: int = 3) -> str:
    return str(n).zfill(width)


# --------------------------- path helpers ----------------------------------

BASE_ROOT = Path(PAGEDIR)

def page_dir_for(uuid_: str) -> Path:
    prefix = uuid_[:2]
    return Path(BASE_ROOT) / prefix / uuid_

# --------------------------- metadata helpers ------------------------------

def _meta_path(page_dir: Path) -> Path:
    return page_dir / "meta.json"

def _read_file_content(file_path: Path) -> str:
    """
    Helper function to read the content of a file.

    Args:
        file_path (Path): Path to the file.

    Returns:
        str: Content of the file.
    """
    return file_path.read_text(encoding="utf-8")

def load_meta(page_dir: Path) -> Dict[str, Any]:
    """
    Load metadata from the meta.json file in the page directory.

    Args:
        page_dir (Path): Path to the page directory.

    Returns:
        Dict[str, Any]: Metadata dictionary.
    """
    p = _meta_path(page_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(_read_file_content(p))
    except json.JSONDecodeError:
        return {}

def save_meta(page_dir: Path, meta: Dict[str, Any]) -> None:
    """
    Save metadata to the meta.json file in the page directory.

    Args:
        page_dir (Path): Path to the page directory.
        meta (Dict[str, Any]): Metadata dictionary to save.
    """
    ensure_dir(page_dir)
    _meta_path(page_dir).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

# --------------------------- core ops --------------------------------------

def _next_diff_index(diffs_dir: Path) -> int:
    """
    Get the next available diff index in the diffs directory.

    Args:
        diffs_dir (Path): Path to the diffs directory.

    Returns:
        int: Next available diff index.
    """
    if not diffs_dir.exists():
        return 1
    nums = [int(p.stem) for p in diffs_dir.iterdir() if p.is_file() and p.suffix == ".diff" and p.stem.isdigit()]
    return (max(nums) + 1) if nums else 1

def _sorted_diff_files(diffs_dir: Path) -> List[Path]:
    files = [p for p in diffs_dir.iterdir() if p.is_file() and p.suffix == ".diff"]
    return sorted(files, key=lambda p: int(p.stem))

def apply_diffs_to_text(base_text: str, diff_file_paths: List[Path]) -> str:
    """
    Apply a series of diffs to the base text to reconstruct the latest text.

    Args:
        base_text (str): The base text content.
        diff_file_paths (List[Path]): List of diff file paths.

    Returns:
        str: The reconstructed text after applying diffs.
    """
    text_lines = base_text.splitlines(keepends=False)
    for diff_path in diff_file_paths:
        diff_text = _read_file_content(diff_path).splitlines(keepends=False)
        text_lines = list(difflib.restore(diff_text, 2))
    return "\n".join(text_lines) + ("\n" if text_lines else "")

# Optimization: Refactored repeated function calls into reusable helper functions.

def _get_or_create_diffs_dir(page_dir: Path) -> Path:
    """
    Ensure the diffs directory exists and return its path.

    Args:
        page_dir (Path): Path to the page directory.

    Returns:
        Path: Path to the diffs directory.
    """
    diffs_dir = page_dir / "diffs"
    ensure_dir(diffs_dir)
    return diffs_dir

def _get_base_and_latest_paths(page_dir: Path) -> Tuple[Path, Path]:
    """
    Get the paths for base.md and latest.md files in the page directory.

    Args:
        page_dir (Path): Path to the page directory.

    Returns:
        Tuple[Path, Path]: Paths to base.md and latest.md files.
    """
    return page_dir / "base.md", page_dir / "latest.md"

# Optimization: Refactored database schema creation into a reusable function.

def _ensure_pages_index_table(cursor: sqlite3.Cursor) -> None:
    """
    Ensure the pages_index table exists with the correct schema.

    Args:
        cursor (sqlite3.Cursor): SQLite cursor to execute the schema creation.
    """
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pages_index (
            UUID TEXT NOT NULL PRIMARY KEY,
            GENRE TEXT NOT NULL,
            AUTHOR TEXT NOT NULL,
            DATE_CREATED TEXT NOT NULL,
            PREVIEW TEXT NOT NULL,
            PREFIX TEXT NOT NULL
        )
        """
    )

# --------------------------- public API ------------------------------------

def init_page(title: str, author: str, genre: str, base_text: str, id_: Optional[str] = None) -> str:
    if not id_:
        id_ = str(uuidlib.uuid4())
    page_dir = page_dir_for(id_)
    diffs_dir = page_dir / "diffs"
    ensure_dir(diffs_dir)
    base_path = page_dir / "base.md"
    latest_path = page_dir / "latest.md"

    base_path.write_text(base_text, encoding="utf-8")
    latest_path.write_text(base_text, encoding="utf-8")

    meta = {
        "uuid": id_,
        "title": title or "",
        "author": author or "",
        "genre" : genre or "article",
        "date": now_iso(),
        "version": 0,
        "baseHash": sha256_of_text(base_text),
        "latestHash": sha256_of_text(base_text),
        "diffCount": 0,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    save_meta(page_dir, meta)

    return id_

def commit_diff(id_: str, new_text: str, author: str, message: str) -> str:
    page_dir = page_dir_for(id_)
    if not page_dir.exists():
        raise FileNotFoundError("page not found; run init_page first")

    base_path, latest_path = _get_base_and_latest_paths(page_dir)
    diffs_dir = _get_or_create_diffs_dir(page_dir)

    old_text = latest_path.read_text(encoding="utf-8") if latest_path.exists() else base_path.read_text(encoding="utf-8")
    old_lines = old_text.splitlines(keepends=False)
    new_lines = new_text.splitlines(keepends=False)
    ndiff = list(difflib.ndiff(old_lines, new_lines))
    diff_text = "\n".join(ndiff)
    diff_hash = sha256_of_text(diff_text)

    idx = _next_diff_index(diffs_dir)
    idx_s = zero_pad(idx)
    diff_file = diffs_dir / f"{idx_s}.diff"
    meta_file = diffs_dir / f"{idx_s}.json"

    diff_file.write_text(diff_text, encoding="utf-8")
    diff_meta = {
        "index": idx,
        "file": diff_file.name,
        "author": author,
        "message": message,
        "createdAt": now_iso(),
        "diffHash": diff_hash,
    }
    meta_file.write_text(json.dumps(diff_meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # update page meta
    meta = load_meta(page_dir)
    meta["diffCount"] = meta.get("diffCount", 0) + 1
    meta["version"] = meta["diffCount"]
    meta["latestHash"] = None
    meta["updatedAt"] = now_iso()
    save_meta(page_dir, meta)

    # rebuild latest and canonical file
    rebuild_latest(id_)
    return diff_file.name

def rebuild_latest(id_: str) -> Path:
    page_dir = page_dir_for(id_)
    if not page_dir.exists():
        raise FileNotFoundError("page not found")

    base_path, latest_path = _get_base_and_latest_paths(page_dir)
    diffs_dir = _get_or_create_diffs_dir(page_dir)
    base_text = base_path.read_text(encoding="utf-8")
    diff_files = _sorted_diff_files(diffs_dir) if diffs_dir.exists() else []
    new_text = apply_diffs_to_text(base_text, diff_files)

    tmp = page_dir / ".latest.tmp"
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(latest_path)

    meta = load_meta(page_dir)
    meta["latestHash"] = sha256_of_text(new_text)
    meta["updatedAt"] = now_iso()
    save_meta(page_dir, meta)

    return latest_path

def view_version(id_: str, index: Optional[int] = None) -> str:
    page_dir = page_dir_for(id_)
    base_path = page_dir / "base.md"
    diffs_dir = page_dir / "diffs"
    base_text = base_path.read_text(encoding="utf-8")
    if index is None:
        diff_files = _sorted_diff_files(diffs_dir) if diffs_dir.exists() else []
    elif index <= 0:
        diff_files = []
    else:
        all_files = _sorted_diff_files(diffs_dir) if diffs_dir.exists() else []
        diff_files = all_files[:index]
    return apply_diffs_to_text(base_text, diff_files)

def list_diffs(id_: str) -> List[Tuple[str, Dict[str, Any]]]:
    page_dir = page_dir_for(id_)
    diffs_dir = page_dir / "diffs"
    out: List[Tuple[str, Dict[str, Any]]] = []
    if not diffs_dir.exists():
        return out
    for p in _sorted_diff_files(diffs_dir):
        metaf = p.with_suffix(".json")
        meta = json.loads(metaf.read_text(encoding="utf-8")) if metaf.exists() else {}
        out.append((p.name, meta))
    return out

def indexToDB(folder_path: Path):
    """
    Recursively scan a folder for UUIDs and index the data into the database.

    Args:
        folder_path (Path): The root folder to scan for UUIDs.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Ensure the table exists
    _ensure_pages_index_table(cursor)

    total = 0
    # Scan only the first-level subdirectories (prefix folders)
    try:
        for prefix_folder in os.listdir(folder_path):
            prefix_path = os.path.join(folder_path, prefix_folder)

            if os.path.isdir(prefix_path):

                for uuid_folder in os.listdir(prefix_path):

                    uuid_path = os.path.join(prefix_path, uuid_folder)

                    if os.path.isdir(uuid_path):

                        meta_path = os.path.join(uuid_path, "meta.json")
                        contents = os.path.join(uuid_path, "latest.md")

                        if os.path.exists(meta_path) and os.path.exists(contents):

                            with open(contents, "r", encoding="utf-8") as f:
                                content_text = f.read()
                                words = content_text.split()
                                preview = " ".join(words[:PREVIEWWORD])

                            with open(meta_path, "r", encoding="utf-8") as f:
                                meta = json.load(f)
                                uuid = meta.get("uuid", "")
                                genre = meta.get("genre", "")
                                author = meta.get("author", "")
                                date_created = meta.get("createdAt", "")
                                prefix = prefix_folder

                            # Insert the data into the table
                            cursor.execute(
                                """
                                INSERT INTO pages_index (UUID, GENRE, AUTHOR, DATE_CREATED, PREVIEW, PREFIX)
                                VALUES (?, ?, ?, ?, ?, ?)
                                ON CONFLICT(UUID) DO UPDATE SET
                                    GENRE = excluded.GENRE,
                                    AUTHOR = excluded.AUTHOR,
                                    DATE_CREATED = excluded.DATE_CREATED,
                                    PREVIEW = excluded.PREVIEW,
                                    PREFIX = excluded.PREFIX
                                """,
                                (uuid, genre, author, date_created, preview, prefix)
                            )
                            total += 1
        conn.commit()
        conn.close()
        print(f"Indexed {total} page(s) in folder: {folder_path}")

    except Exception as e:
        print(f"Error during indexing: {e}")

def insertPage(page_path: Path) -> bool:
    """
    Insert a single page directory (containing `meta.json`) into the pages_index database.

    Args:
        page_path (Path): Path to the page folder (the UUID directory).

    Returns:
        bool: True if insertion succeeded or the record already existed, False on error or missing meta.json.
    """
    try:
        # Ensure DB folder exists
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Ensure the table exists with the correct schema
        _ensure_pages_index_table(cursor)

        meta_path = page_path / "meta.json"
        if not meta_path.exists():
            # nothing to insert
            conn.close()
            return False

        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)

        contents = page_path / "latest.md"
        if not contents.exists():
            conn.close()
            return False

        with contents.open("r", encoding="utf8") as d:
            content_text = d.read()
            words = content_text.split()
            preview = " ".join(words[:PREVIEWWORD])

        uuid = meta.get("uuid", "")
        genre = meta.get("genre", "")
        author = meta.get("author", "")
        date_created = meta.get("createdAt", "")
        prefix = page_path.parent.name

        cursor.execute(
            """
            INSERT INTO pages_index (UUID, GENRE, AUTHOR, DATE_CREATED, PREVIEW, PREFIX)
            SELECT ?, ?, ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM pages_index WHERE UUID = ?
            )
            """,
            (uuid, genre, author, date_created, preview, prefix, uuid),
        )

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error inserting page {page_path}: {e}")
        return False

def search_uuid_in_path(uuid: str, folder_path: Path) -> Optional[Dict[str, Any]]:
    """
    Search for a UUID in the specified path and retrieve its metadata from the database.

    Args:
        uuid (str): The UUID to search for.
        folder_path (Path): The path to search within.

    Returns:
        Optional[Dict[str, Any]]: Metadata for the UUID if found, otherwise None.
    """
    # Ensure the database file exists
    if not DB_FILE.exists():
        print("Database file not found.")
        return None

    # Check if the UUID exists in the specified path
    uuid_path = folder_path / uuid[:2] / uuid
    meta_path = uuid_path / "meta.json"
    if not meta_path.exists():
        return None

    # Query the database for the UUID
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT UUID, GENRE, AUTHOR, DATE_CREATED, PREVIEW, PREFIX
        FROM pages_index
        WHERE UUID = ?
        """,
        (uuid,)
    )
    result = cursor.fetchone()
    conn.close()

    if result:
        metadata = {
            "UUID": result[0],
            "Genre": result[1],
            "Author": result[2],
            "Date Created": result[3],
            "Preview": result[4],
            "Prefix": result[5],
        }
        return metadata
    return None

def get_latest_text(id_: str) -> str:
    """
    Retrieve the latest text content of a page by its UUID.

    Args:
        id_ (str): The UUID of the page.

    Returns:
        str: The latest text content of the page.
    """
    page_dir = page_dir_for(id_)
    latest_path = page_dir / "latest.md"

    if not latest_path.exists():
        raise FileNotFoundError("Latest version not found; ensure the page is initialized and rebuilt.")

    return latest_path.read_text(encoding="utf-8")

def listPage(offset: int = 0, limit: int = 10, query: str = "") -> Dict[str, Any]:
    """
    Fetch a paginated list of pages from the database using preview data only.

    Args:
        offset (int): The starting point for pagination.
        limit (int): The maximum number of items to fetch.
        query (str): A search query to filter results by title or creator.

    Returns:
        Dict[str, Any]: A dictionary containing the list of items and the total count.
    """
    where = ""
    params_select: List[Any] = []
    params_count: List[Any] = []

    if query:
        where = " WHERE title LIKE ? OR author LIKE ?"
        qparam = f"%{query}%"
        params_select.extend([qparam, qparam])
        params_count.extend([qparam, qparam])

    sql_count = f"SELECT COUNT(*) FROM pages_index{where}"
    sql = f"SELECT UUID, GENRE, AUTHOR, DATE_CREATED, PREVIEW FROM pages_index{where} ORDER BY DATE_CREATED DESC LIMIT ? OFFSET ?"

    conn = sqlite3.connect(DB_FILE)
    try:
        cursor = conn.execute(sql_count, params_count)
        total = cursor.fetchone()[0]

        params = list(params_select) + [limit, offset]
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()

        # Convert rows to dictionaries using column names
        column_names = [description[0] for description in cursor.description]
        items = [dict(zip(column_names, row)) for row in rows]

        return {
            "items": items,
            "total": total
        }
    finally:
        conn.close()

# --------------------------- CLI -------------------------------------------

def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manage markdown versions with hybrid diffs + rolling latest.")
    sub = p.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="initialize a page")
    p_init.add_argument("uuid", nargs="?", help="uuid (default: generated)")
    p_init.add_argument("title", nargs="?", default="", help="title")
    p_init.add_argument("author", nargs="?", default="", help="author")
    p_init.add_argument("genre", nargs="?", default="article", help="genre")
    p_init.add_argument("file", nargs="?", help="file path for base content")

    p_commit = sub.add_parser("commit", help="commit a new version from content")
    p_commit.add_argument("uuid", help="page uuid")
    p_commit.add_argument("file", help="file with new content")
    p_commit.add_argument("author", nargs="?", default="", help="author")
    p_commit.add_argument("message", nargs="?", default="", help="message")

    p_view = sub.add_parser("view", help="view a version to stdout")
    p_view.add_argument("uuid", help="page uuid")
    p_view.add_argument("index", nargs="?", type=int, help="diff index to view (None=latest)")

    p_rebuild = sub.add_parser("rebuild", help="rebuild latest for page")
    p_rebuild.add_argument("uuid", help="page uuid")

    p_list = sub.add_parser("list-diffs", help="list diffs for a page")
    p_list.add_argument("uuid", help="page uuid")
    
    p_index = sub.add_parser("index", help="index pages into the database")
    p_index.add_argument("folder", nargs="?", default="data/pages", help="folder path to index")
    
    p_delete = sub.add_parser("delete", help="delete a page")
    p_delete.description = "Delete command cannot be used in this operation, please use the appropriate method."

    p_search = sub.add_parser("search", help="search for a uuid in the database")
    p_search.add_argument("uuid", help="page uuid")
    
    return p

def _read_text_file(path_str: str) -> str:
    p = Path(path_str)
    return p.read_text(encoding="utf-8")

def main(argv: Optional[List[str]] = None) -> int:
    p = _make_parser()
    args = p.parse_args(argv)
    if not args.cmd:
        p.print_help()
        return 1

    if args.cmd == "init":
        content = _read_text_file(args.file) if args.file else ""
        uuid = init_page(title=(args.title or ""), author=(args.author or ""), genre=(args.genre or ""), base_text=content, id_=args.uuid)
        print(f"Initialized page with UUID: {uuid}")
        return 0

    if args.cmd == "commit":
        content = _read_text_file(args.file)
        commit_diff(id_=args.uuid, new_text=content, author=args.author, message=args.message)
        return 0

    if args.cmd == "view":
        txt = get_latest_text(id_=args.uuid)
        print(txt)
        return 0

    if args.cmd == "rebuild":
        rebuild_latest(id_=args.uuid)
        return 0

    if args.cmd == "list-diffs":
        for name, meta in list_diffs(id_=args.uuid):
            print(name, json.dumps(meta, ensure_ascii=False))
        return 0

    if args.cmd == "delete":
        print("Delete command cannot be used in this operation, please use the appropriate method.")
        return 1
    
    if args.cmd == "index":
        os.makedirs(BASE_ROOT, exist_ok=True)
        indexToDB(BASE_ROOT)
        return 0
    
    if args.cmd == "search":
        folder_path = Path(BASE_ROOT)
        metadata = search_uuid_in_path(args.uuid, folder_path)
        if metadata:
            print("Metadata found:")
            for key, value in metadata.items():
                print(f"{key}: {value}")
            return 0
        else:
            print("UUID not found.")
            return 1

    p.print_help()
    return 1

# Example usage for indexing
if __name__ == "__main__":
    raise SystemExit(main())