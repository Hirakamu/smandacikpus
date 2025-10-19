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
from config import PAGEDIR

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
    return Path("data/pages") / prefix / uuid_

# --------------------------- metadata helpers ------------------------------

def _meta_path(page_dir: Path) -> Path:
    return page_dir / "meta.json"

def load_meta(page_dir: Path) -> Dict[str, Any]:
    p = _meta_path(page_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_meta(page_dir: Path, meta: Dict[str, Any]) -> None:
    ensure_dir(page_dir)
    _meta_path(page_dir).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

# --------------------------- core ops --------------------------------------

def _next_diff_index(diffs_dir: Path) -> int:
    if not diffs_dir.exists():
        return 1
    nums: List[int] = []
    for p in diffs_dir.iterdir():
        if p.is_file() and p.suffix == ".diff":
            try:
                nums.append(int(p.stem))
            except Exception:
                pass
    return (max(nums) + 1) if nums else 1

def _sorted_diff_files(diffs_dir: Path) -> List[Path]:
    files = [p for p in diffs_dir.iterdir() if p.is_file() and p.suffix == ".diff"]
    return sorted(files, key=lambda p: int(p.stem))

def apply_diffs_to_text(base_text: str, diff_file_paths: List[Path]) -> str:
    text_lines = base_text.splitlines(keepends=False)
    for diff_path in diff_file_paths:
        diff_text = diff_path.read_text(encoding="utf-8").splitlines(keepends=False)
        text_lines = list(difflib.restore(diff_text, 2))  # reconstruct new
    return "\n".join(text_lines) + ("\n" if text_lines else "")

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

    base_path = page_dir / "base.md"
    latest_path = page_dir / "latest.md"
    diffs_dir = page_dir / "diffs"
    ensure_dir(diffs_dir)

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

    base_path = page_dir / "base.md"
    latest_path = page_dir / "latest.md"
    diffs_dir = page_dir / "diffs"
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

def index_pages(base_dir: Path) -> List[Dict[str, Any]]:
    """
    Index all pages by UUID, folder path, and metadata.

    Args:
        base_dir (Path): The base directory to start indexing from.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing UUID, folder path, and metadata.
    """
    index = []

    for root, dirs, files in os.walk(base_dir):
        # Check if the folder contains a meta.json file
        if "meta.json" in files:
            meta_path = Path(root) / "meta.json"
            try:
                # Load metadata
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                uuid = meta.get("uuid")
                if uuid:
                    index.append({
                        "uuid": uuid,
                        "folder": str(Path(root).relative_to(base_dir)),
                        "meta": meta
                    })
            except Exception as e:
                print(f"Error reading meta.json in {root}: {e}")

    return index

def save_index(index: List[Dict[str, Any]], output_path: Path) -> None:
    """
    Save the index to a JSON file.

    Args:
        index (List[Dict[str, Any]]): The index data to save.
        output_path (Path): The path to the output JSON file.
    """
    try:
        output_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Index saved to {output_path}")
    except Exception as e:
        print(f"Error saving index to {output_path}: {e}")

def setup_database(db_path: Path) -> None:
    """
    Set up the database schema for indexing pages.

    Args:
        db_path (Path): The path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS page_index (
            uuid TEXT PRIMARY KEY,
            folder TEXT NOT NULL,
            metadata TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

def index_pages_to_db(base_dir: Path, db_path: Path) -> None:
    """
    Index all pages by UUID, folder path, and metadata into a database.

    Args:
        base_dir (Path): The base directory to start indexing from.
        db_path (Path): The path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for root, dirs, files in os.walk(base_dir):
        # Check if the folder contains a meta.json file
        if "meta.json" in files:
            meta_path = Path(root) / "meta.json"
            try:
                # Load metadata
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                uuid = meta.get("uuid")
                if uuid:
                    folder = str(Path(root).relative_to(base_dir))
                    metadata = json.dumps(meta, ensure_ascii=False)
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO page_index (uuid, folder, metadata)
                        VALUES (?, ?, ?)
                        """,
                        (uuid, folder, metadata)
                    )
            except Exception as e:
                print(f"Error reading meta.json in {root}: {e}")

    conn.commit()
    conn.close()

# --------------------------- CLI -------------------------------------------

def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manage markdown versions with hybrid diffs + rolling latest + canonical writes.")
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
        txt = view_version(id_=args.uuid, index=args.index)
        print(txt, end="")
        return 0

    if args.cmd == "rebuild":
        rebuild_latest(id_=args.uuid)
        return 0

    if args.cmd == "list-diffs":
        for name, meta in list_diffs(id_=args.uuid):
            print(name, json.dumps(meta, ensure_ascii=False))
        return 0

    p.print_help()
    return 1

# Example usage for indexing
if __name__ == "__main__":
    base_dir = BASE_ROOT / "data/pages"
    output_path = BASE_ROOT / "index.json"
    db_path = BASE_ROOT / "index.db"

    index = index_pages(base_dir)
    save_index(index, output_path)

    setup_database(db_path)
    index_pages_to_db(base_dir, db_path)

    raise SystemExit(main())