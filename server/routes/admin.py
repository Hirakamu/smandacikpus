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
import datacontroller as datac

bp = Blueprint("admin", __name__)

@bp.route('/admin')
def adminPage():
    if not session.get("logged_in"):
        return redirect(url_for("admin.login"))
    return render_template('admin.html')

@bp.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Example: Hardcoded admin credentials
        if username == 'admin' and password == 'password':
            session['logged_in'] = True
            flash("Login successful!", "success")
            return redirect(url_for("admin.adminPage"))
        else:
            flash("Invalid credentials!", "danger")

    return render_template('login.html')

