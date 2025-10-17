#!/usr/bin/env python3
"""
manage_versions.py

Features:
- content/pages/YYYY/MM/DD/<uuid> structure
- dashed uuid (uuid4)
- base.md, latest.md, diffs/NNN.diff + NNN.json (diff metadata)
- SHA-256 hashing for blobs and diffs
- diffs produced with difflib.ndiff and applied with difflib.restore
- rolling rebuild: on new diff, rebuild latest.md from base + all diffs
- view arbitrary version without writing
"""

import os
import sys
import json
import uuid
import argparse
import hashlib
import datetime
import difflib
from pathlib import Path

# --- utilities ---------------------------------------------------------------

def now_iso():
    return datetime.datetime.now().astimezone().isoformat()

def sha256_of_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_of_text(s: str) -> str:
    return sha256_of_bytes(s.encode("utf-8"))

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def zero_pad(n, width=3):
    return str(n).zfill(width)

# --- path helpers ------------------------------------------------------------

BASE_ROOT = Path("content") / "pages"

def page_dir_for(date_iso: str, id_: str):
    # date_iso: "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS..." -> take date part
    d = date_iso.split("T")[0]
    y, m, d = d.split("-")
    return BASE_ROOT / y / m / d / id_

# --- metadata helpers -------------------------------------------------------

def load_meta(page_dir: Path):
    meta_path = page_dir / "meta.json"
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))

def save_meta(page_dir: Path, meta: dict):
    ensure_dir(page_dir)
    (page_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

# --- core operations --------------------------------------------------------

def init_page(date_iso: str, title: str, author: str, base_text: str, id_: str = None):
    if id_ is None:
        id_ = str(uuid.uuid4())  # dashed uuid
    page_dir = page_dir_for(date_iso, id_)
    ensure_dir(page_dir)
    # files
    base_path = page_dir / "base.md"
    latest_path = page_dir / "latest.md"
    diffs_dir = page_dir / "diffs"
    ensure_dir(diffs_dir)
    # write base/latest
    base_path.write_text(base_text, encoding="utf-8")
    latest_path.write_text(base_text, encoding="utf-8")
    # meta
    meta = {
        "uuid": id_,
        "title": title,
        "author": author,
        "date": date_iso,
        "version": 0,
        "baseHash": sha256_of_text(base_text),
        "latestHash": sha256_of_text(base_text),
        "diffCount": 0,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    save_meta(page_dir, meta)
    print(f"initialized page {id_} at {page_dir}")
    return id_

def _next_diff_index(diffs_dir: Path):
    files = [p.name for p in diffs_dir.iterdir() if p.is_file() and p.name.endswith(".diff")]
    if not files:
        return 1
    nums = []
    for f in files:
        try:
            nums.append(int(Path(f).stem))
        except Exception:
            pass
    return max(nums) + 1 if nums else 1

def commit_diff(date_iso: str, id_: str, new_text: str, author: str, message: str):
    page_dir = page_dir_for(date_iso, id_)
    if not page_dir.exists():
        raise FileNotFoundError("page not found; run init first")
    base_path = page_dir / "base.md"
    diffs_dir = page_dir / "diffs"
    ensure_dir(diffs_dir)
    latest_path = page_dir / "latest.md"
    # compute old text to diff against. Use latest.md for author flow, but rebuild uses base+all diffs
    old_text = latest_path.read_text(encoding="utf-8") if latest_path.exists() else base_path.read_text(encoding="utf-8")
    old_lines = old_text.splitlines(keepends=False)
    new_lines = new_text.splitlines(keepends=False)
    ndiff = list(difflib.ndiff(old_lines, new_lines))
    diff_text = "\n".join(ndiff) + ("\n" if ndiff and not ndiff[-1].endswith("\n") else "")
    diff_hash = sha256_of_text(diff_text)
    idx = _next_diff_index(diffs_dir)
    idx_s = zero_pad(idx, width=3)
    diff_file = diffs_dir / f"{idx_s}.diff"
    meta_file = diffs_dir / f"{idx_s}.json"
    # write diff and meta
    diff_file.write_text(diff_text, encoding="utf-8")
    diff_meta = {
        "index": idx,
        "file": diff_file.name,
        "author": author,
        "message": message,
        "createdAt": now_iso(),
        "diffHash": diff_hash
    }
    meta_file.write_text(json.dumps(diff_meta, indent=2, ensure_ascii=False), encoding="utf-8")
    # update meta.json
    meta = load_meta(page_dir)
    meta.setdefault("diffCount", 0)
    meta["diffCount"] = meta.get("diffCount", 0) + 1
    meta["version"] = meta["diffCount"]
    meta["latestHash"] = None  # will update after rebuild
    meta["updatedAt"] = now_iso()
    save_meta(page_dir, meta)
    # rebuild latest from base + all diffs
    rebuild_latest(date_iso, id_)
    print(f"committed diff {diff_file.name} by {author}")
    return diff_file.name

def _sorted_diff_files(diffs_dir: Path):
    files = [p for p in diffs_dir.iterdir() if p.is_file() and p.suffix == ".diff"]
    return sorted(files, key=lambda p: int(p.stem))

def apply_diffs_to_text(base_text: str, diff_file_paths):
    text_lines = base_text.splitlines(keepends=False)
    for diff_path in diff_file_paths:
        diff_text = diff_path.read_text(encoding="utf-8").splitlines(keepends=False)
        # difflib.restore with which=2 reconstructs the second sequence (the patched/new file)
        text_lines = list(difflib.restore(diff_text, 2))
    return "\n".join(text_lines) + ("\n" if text_lines else "")

def rebuild_latest(date_iso: str, id_: str):
    page_dir = page_dir_for(date_iso, id_)
    if not page_dir.exists():
        raise FileNotFoundError("page not found")
    base_path = page_dir / "base.md"
    latest_path = page_dir / "latest.md"
    diffs_dir = page_dir / "diffs"
    base_text = base_path.read_text(encoding="utf-8")
    diff_files = _sorted_diff_files(diffs_dir) if diffs_dir.exists() else []
    new_text = apply_diffs_to_text(base_text, diff_files)
    # overwrite latest atomically
    tmp = page_dir / ".latest.tmp"
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(latest_path)
    # update meta
    meta = load_meta(page_dir)
    meta["latestHash"] = sha256_of_text(new_text)
    meta["updatedAt"] = now_iso()
    save_meta(page_dir, meta)
    return latest_path

def view_version(date_iso: str, id_: str, index: int = None):
    """Return the text at a certain diff index.
       index=None -> latest (all diffs).
       index=0 -> base only.
       index=N -> after applying first N diffs.
    """
    page_dir = page_dir_for(date_iso, id_)
    base_path = page_dir / "base.md"
    diffs_dir = page_dir / "diffs"
    base_text = base_path.read_text(encoding="utf-8")
    if index is None:
        diff_files = _sorted_diff_files(diffs_dir) if diffs_dir.exists() else []
    else:
        all_files = _sorted_diff_files(diffs_dir) if diffs_dir.exists() else []
        diff_files = all_files[:index]
    return apply_diffs_to_text(base_text, diff_files)

def list_diffs(date_iso: str, id_: str):
    page_dir = page_dir_for(date_iso, id_)
    diffs_dir = page_dir / "diffs"
    out = []
    for p in _sorted_diff_files(diffs_dir):
        metaf = p.with_suffix(".json")
        meta = json.loads(metaf.read_text(encoding="utf-8")) if metaf.exists() else {}
        out.append((p.name, meta))
    return out

# --- CLI --------------------------------------------------------------------

def cli_init(args):
    id_ = args.uuid if args.uuid else None
    date_iso = args.date or datetime.date.today().isoformat()
    base_text = args.file.read_text(encoding="utf-8") if args.file else (args.content or "")
    init_page(date_iso=date_iso, title=args.title or "", author=args.author or "unknown", base_text=base_text, id_=id_)
    
def cli_commit(args):
    date_iso = args.date or datetime.date.today().isoformat()
    if args.file:
        new_text = args.file.read_text(encoding="utf-8")
    else:
        new_text = args.content or ""
    name = commit_diff(date_iso=date_iso, id_=args.uuid, new_text=new_text, author=args.author or "unknown", message=args.message or "")
    print(name)

def cli_view(args):
    date_iso = args.date or datetime.date.today().isoformat()
    txt = view_version(date_iso=date_iso, id_=args.uuid, index=(None if args.index is None else int(args.index)))
    sys.stdout.write(txt)

def cli_rebuild(args):
    date_iso = args.date or datetime.date.today().isoformat()
    p = rebuild_latest(date_iso=date_iso, id_=args.uuid)
    print(f"rebuilt latest -> {p}")

def cli_meta(args):
    date_iso = args.date or datetime.date.today().isoformat()
    page_dir = page_dir_for(date_iso, args.uuid)
    print(json.dumps(load_meta(page_dir), indent=2, ensure_ascii=False))

def cli_list(args):
    date_iso = args.date or datetime.date.today().isoformat()
    for name, meta in list_diffs(date_iso=date_iso, id_=args.uuid):
        print(name, json.dumps(meta, ensure_ascii=False))

def make_parser():
    p = argparse.ArgumentParser(description="Manage markdown versions with diffs + rolling latest.")
    sub = p.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init")
    p_init.add_argument("--date", help="YYYY-MM-DD (default today)")
    p_init.add_argument("--uuid", help="dashed uuid (default generated)")
    p_init.add_argument("--title", help="title")
    p_init.add_argument("--author", help="author")
    p_init.add_argument("--file", type=Path, help="file path for base content")
    p_init.add_argument("--content", help="base content inline (if no file)")

    p_commit = sub.add_parser("commit")
    p_commit.add_argument("uuid", help="page uuid")
    p_commit.add_argument("--date", help="YYYY-MM-DD (folder date)")
    p_commit.add_argument("--file", type=Path, help="file with new content")
    p_commit.add_argument("--content", help="new content inline")
    p_commit.add_argument("--author", help="author of diff")
    p_commit.add_argument("--message", help="commit message")

    p_view = sub.add_parser("view")
    p_view.add_argument("uuid", help="page uuid")
    p_view.add_argument("--date", help="YYYY-MM-DD")
    p_view.add_argument("--index", type=int, help="diff index to view: 0=base, 1=after first diff, None=latest (default)")

    p_rebuild = sub.add_parser("rebuild")
    p_rebuild.add_argument("uuid", help="page uuid")
    p_rebuild.add_argument("--date", help="YYYY-MM-DD")

    p_meta = sub.add_parser("meta")
    p_meta.add_argument("uuid", help="page uuid")
    p_meta.add_argument("--date", help="YYYY-MM-DD")

    p_list = sub.add_parser("list-diffs")
    p_list.add_argument("uuid", help="page uuid")
    p_list.add_argument("--date", help="YYYY-MM-DD")

    return p

def main():
    p = make_parser()
    args = p.parse_args()
    if not args.cmd:
        p.print_help(); sys.exit(1)
    if args.cmd == "init":
        cli_init(args)
    elif args.cmd == "commit":
        cli_commit(args)
    elif args.cmd == "view":
        cli_view(args)
    elif args.cmd == "rebuild":
        cli_rebuild(args)
    elif args.cmd == "meta":
        cli_meta(args)
    elif args.cmd == "list-diffs":
        cli_list(args)
    else:
        p.print_help()

if __name__ == "__main__":
    main()
