from flask import Blueprint, render_template, request, abort
from dbapi import ReadsAPI
from markdown import markdown

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
        articles=items,
        page=page,
        total=len(items),
        q=q,
        limit=limit,
    )


@bp.route("/baca/<uuid>")
def read(uuid: str):
    p = ReadsAPI.read(uuid)
    if not p:
        abort(404)

    p["content"] = markdown(p["content"], extensions=["fenced_code", "tables"])
    return render_template("baca.html", page=p)