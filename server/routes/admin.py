from flask import (
    Blueprint,
    request,
    jsonify,
    abort,
    render_template,
    redirect,
    url_for,
    session,
    current_app,
    flash
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import uuid
import os
import html
from config import DB_FILE, PAGEDIR, ADMIN_REGISTER_TOKEN, SESSION_LIFETIME_DAYS

bp = Blueprint("admin", __name__)

@bp.route('/admin')
def adminPage():
    return render_template('admin.html')