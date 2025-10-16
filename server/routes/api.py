from flask import Blueprint, request, jsonify, render_template
from typing import Any
from dbapi import ReadsAPI
from errors import register_error_handlers

bp = Blueprint('api', __name__)
register_error_handlers(bp)

def error(code: int, message: str): # complete
    return render_template('error.html', code=code, message=message), code

@bp.route('/api/page/import') # complete
def readsImport():
    res = ReadsAPI.importFromDir()
    return jsonify({"status": f"{res}"})

@bp.route('/api/ping')
def ping():
    return jsonify({"status": 200, "description": "received"})
