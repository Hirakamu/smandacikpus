from flask import Blueprint, render_template, request, abort, render_template_string, jsonify
from dbapi import ReadsAPI
from markdown import markdown
from functools import lru_cache
import datetime, json, csv, smtplib

bp = Blueprint("site", __name__)

@bp.route("/")
def home():
    q = request.args.get('q', '') or ''
    page = max(1, int(request.args.get('page',1)))
    limit = 10
    offset = (page - 1) * limit
    data = ReadsAPI.pageList(offset,limit,q)
    items = data.get("items", [])
    
    for a in items:
        if "uuid" in a:
            a["uuid"] = a["uuid"].replace("-", "")
    
    return render_template(
        "index.html",
        articles=items
    )


@bp.route("/baca/<uuid>")
@lru_cache(maxsize=1024)
def read(uuid: str):
    p = ReadsAPI.read(uuid)
    if not p:
        abort(404)

    p["content"] = markdown(p["content"], extensions=["fenced_code", "tables"])
    return render_template("baca.html", page=p)


@bp.route("/baca")
def reads():
    page = int(request.args.get("page", 1))
    q = request.args.get("q", "").strip()

    per_page = 2
    offset = (page - 1) * per_page

    data = ReadsAPI.pageList(offset=offset, limit=per_page, query=q)
    articles = data["items"]
    total = data["total"]
    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "reads.html",
        articles=articles,
        q=q,
        current_page=page,
        total_pages=total_pages
    )



