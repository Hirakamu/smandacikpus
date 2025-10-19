from flask import Flask
from config import ROOT, SESSION_LIFETIME_DAYS, DB_FILE, USERDATA
import os
from datetime import timedelta
from routes.admin import bp as admin_bp
from routes.api import bp as api_bp
from routes.site import bp as site_bp
from errors import register_error_handlers
from dbapi import DButils
from sqlite3 import Connection as sqlite

def create_app():
    os.makedirs(USERDATA, exist_ok=True)
    app = Flask(__name__, static_folder=str(ROOT / 'web/static'), template_folder=str(ROOT / 'web/templates'))
    app.permanent_session_lifetime = timedelta(days=SESSION_LIFETIME_DAYS)
    app.secret_key = "your-unique-secret-key"  # Set a unique and secret key for session management

    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(site_bp)

    register_error_handlers(app)
    
    app.teardown_appcontext(lambda e: DButils.close())  # auto close after request
    DButils.init_db()  # initialize once
    DButils.syncAll()

    return app