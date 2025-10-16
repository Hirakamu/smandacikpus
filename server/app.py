from flask import Flask
from config import ROOT, SESSION_LIFETIME_DAYS, DB_FILE, USERDATA
import os
from datetime import timedelta
#   from routes.admin import bp as admin_bp
from routes.api import bp as api_bp
from routes.site import bp as site_bp
from errors import register_error_handlers
from dbapi import DButils
from sqlite3 import Connection as sqlite

def create_app():
    os.makedirs(USERDATA, exist_ok=True)
    db = sqlite(DB_FILE)
    app = Flask(__name__, static_folder=str(ROOT / 'web/static'), template_folder=str(ROOT / 'web/templates'))
    app.config['JSON_SORT_KEYS'] = False
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
    app.permanent_session_lifetime = timedelta(days=SESSION_LIFETIME_DAYS)

    #app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(site_bp)

    register_error_handlers(app)
    
    app.teardown_appcontext(lambda e: DButils.close())  # auto close after request
    DButils.init_db()  # initialize once

    return app