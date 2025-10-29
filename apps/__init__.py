# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

import os

from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from importlib import import_module
from flask_apscheduler import APScheduler
from flask_wtf.csrf import CSRFProtect #Flask has built-in support for CSRF protection when using the Flask-WTF library: https://flask-wtf.readthedocs.io/en/stable/csrf.html

db = SQLAlchemy()
login_manager = LoginManager()
scheduler = APScheduler()
csrf = CSRFProtect()

def register_extensions(app):
    db.init_app(app)
    login_manager.init_app(app)
    scheduler.init_app(app)
    csrf.init_app(app)


def register_blueprints(app):
    for module_name in ('authentication', 'home', 'api'):
        module = import_module('apps.{}.routes'.format(module_name))
        app.register_blueprint(module.blueprint)


def configure_database(app):

    with app.app_context():
        
    # def initialize_database():
        try:
            db.create_all()
        except Exception as e:

            print('> Error: DBMS Exception: ' + str(e) )

            # fallback to SQLite
            basedir = os.path.abspath(os.path.dirname(__file__))
            app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'db.sqlite3')

            print('> Fallback to SQLite ')
            db.create_all()

    @app.teardown_request
    def shutdown_session(exception=None):
        try:
            db.session.remove()
        except Exception as e:
            print(f"Error during session cleanup: {e}")
    
    @app.teardown_appcontext
    def shutdown_db_connections(exception=None):
        try:
            db.session.close()
        except Exception as e:
            print(f"Error during database connection cleanup: {e}")

# from apps.authentication.oauth import github_blueprint, nylas_bp

def create_app(config):
    app = Flask(__name__)
    app.config.from_object(config)
    register_extensions(app)
    register_blueprints(app)
    configure_database(app)
    return app
