from flask import Flask
from config import ROOT, SESSION_LIFETIME_DAYS, USERDATA
import os
from datetime import timedelta
from routes.admin import bp as admin_bp
from routes.api import bp as api_bp
from routes.site import bp as site_bp
import datacontroller as datac
from errors import register_error_handlers
from dbapi import DButils

def create_app():
    os.makedirs(USERDATA, exist_ok=True)
    app = Flask(__name__, static_folder=str(ROOT / 'web/static'), template_folder=str(ROOT / 'web/templates'))
    app.permanent_session_lifetime = timedelta(days=SESSION_LIFETIME_DAYS)
    app.secret_key = "development-secret"

    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(site_bp)

    register_error_handlers(app)
    
    with app.app_context():
        DButils.init_db()
    
    return app