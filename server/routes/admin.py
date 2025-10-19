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

@bp.route('/admin/logout')
def logout():
    session.pop('logged_in', None)
    flash("Logged out successfully!", "success")
    return redirect(url_for("admin.login"))

@bp.route('/admin/pages')
def managePages():
    if not session.get("logged_in"):
        return redirect(url_for("admin.login"))

    # Fetch pages from the database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT uuid, title, creator, created FROM reads")
    pages = cursor.fetchall()
    conn.close()

    return render_template('manage_pages.html', pages=pages)

@bp.route('/admin/pages/create', methods=['GET', 'POST'])
def createPage():
    if not session.get("logged_in"):
        return redirect(url_for("admin.login"))

    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        uuid_str = str(uuid.uuid4())
        created = datetime.now().isoformat()

        content = content or ""  # Ensure content is not None

        # Ensure title is not None
        title = title or "Untitled"

        # Detect the creator from the session or default to 'admin'
        creator = session.get('username', 'admin')

        # Save to database
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reads (uuid, title, creator, created, type, preview)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (uuid_str, title, creator, created, "article", content[:200])
        )
        conn.commit()
        conn.close()
        
        datac.init_page(date_iso=created, title=title, base_text=content, id_=uuid_str, author=creator)

        flash("Page created successfully!", "success")
        return redirect(url_for("admin.managePages"))

    return render_template('create_page.html')

@bp.route('/admin/pages/delete/<uuid>', methods=['POST'])
def deletePage(uuid):
    if not session.get("logged_in"):
        return redirect(url_for("admin.login"))

    # Delete page from the database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reads WHERE uuid = ?", (uuid,))
    conn.commit()
    conn.close()

    flash("Page deleted successfully!", "success")
    return redirect(url_for("admin.managePages"))

@bp.route('/admin/pages/edit/<uuid>', methods=['GET', 'POST'])
def editPage(uuid):
    if not session.get("logged_in"):
        return redirect(url_for("admin.login"))

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')

        content = content or ""  # Ensure content is not None
        # Update page in the database
        cursor.execute(
            """
            UPDATE reads
            SET title = ?, preview = ?
            WHERE uuid = ?
            """,
            (title, content[:200], uuid)
        )
        conn.commit()
        conn.close()

        flash("Page updated successfully!", "success")
        return redirect(url_for("admin.managePages"))

    # Fetch page details for editing
    cursor.execute("SELECT title, preview, created FROM reads WHERE uuid = ?", (uuid,))
    page = cursor.fetchone()

    if not page:
        conn.close()
        abort(404)

    # Read content from the markdown file
    created_iso = page[2].replace("'", "")
    md_path = Path(PAGEDIR) / datetime.fromisoformat(created_iso).strftime("%Y/%m/%d") / uuid / "latest.md"

    if md_path.exists():
        with md_path.open("r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = page[1]  # Fallback to preview if file doesn't exist

    conn.close()

    return render_template('edit_page.html', page=(page[0], content), uuid=uuid)