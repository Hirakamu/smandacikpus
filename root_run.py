"""Simple runner to start the rootfolder scaffold app for testing.

Usage: python root_run.py
"""
from rootfolder.app import create_app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=True)
