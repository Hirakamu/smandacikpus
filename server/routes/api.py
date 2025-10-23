from flask import Blueprint, jsonify, render_template
from errors import register_error_handlers

bp = Blueprint('api', __name__)
register_error_handlers(bp)

def error(code: int, message: str): # complete
    return render_template('error.html', code=code, message=message), code

@bp.route('/api/ping') # complete
def ping():
    return jsonify({"status": 200, "description": "received"})