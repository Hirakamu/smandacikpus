from flask import Blueprint, render_template, request, abort, render_template_string, jsonify
from markdown import markdown
from functools import lru_cache
import datacontroller as datac

bp = Blueprint("site", __name__)

@bp.route("/")
def home():
    return render_template("home.html", data=None)



@bp.route("/baca/<uuid>")
@lru_cache(maxsize=1024)
def read(uuid: str):
    return render_template("baca.html")


@bp.route("/ujian")
def exam():
    return render_template("exam.html")