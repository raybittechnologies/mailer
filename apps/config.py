# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

import os, random, string
from datetime import timedelta
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

class Config(object):
    basedir = os.path.abspath(os.path.dirname(__file__))

    # Assets Management
    ASSETS_ROOT = os.getenv('ASSETS_ROOT', '/static/assets')

    # Set up the App SECRET_KEY
    SECRET_KEY = os.getenv('SECRET_KEY', "my super secret key")
    if not SECRET_KEY:
        print("No secret key found")
        SECRET_KEY = ''.join(random.choice(string.ascii_lowercase) for i in range(32))

    SOCIAL_AUTH_GITHUB = False

    GITHUB_ID = os.getenv('GITHUB_ID')
    GITHUB_SECRET = os.getenv('GITHUB_SECRET')

    # Enable/Disable Github Social Login    
    if GITHUB_ID and GITHUB_SECRET:
        SOCIAL_AUTH_GITHUB = True

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # DB_ENGINE = os.getenv('DB_ENGINE', None)
    # DB_USERNAME = os.getenv('DB_USERNAME', None)
    # DB_PASS = os.getenv('DB_PASS', None)
    # DB_HOST = os.getenv('DB_HOST', None)
    # DB_PORT = os.getenv('DB_PORT', None)
    # DB_NAME = os.getenv('DB_NAME', None)

    DB_ENGINE='mysql+pymysql'
    DB_HOST='db-mysql-nyc3-11639-do-user-14397341-0.c.db.ondigitalocean.com'
    DB_NAME='roboticbookingagent'
    DB_USERNAME='doadmin'
    DB_PASS='AVNS_S3pYq2o2fp0kYBbEDbv'
    DB_PORT=25060


    USE_SQLITE = True
    
    WEB_HOST_IP = os.getenv("WEB_HOST_IP", None)

    # try to set up a Relational DBMS
    if DB_ENGINE and DB_NAME and DB_USERNAME:

        try:

            # Relational DBMS: PSQL, MySql
            SQLALCHEMY_DATABASE_URI = '{}://{}:{}@{}:{}/{}'.format(
                DB_ENGINE,
                DB_USERNAME,
                DB_PASS,
                DB_HOST,
                DB_PORT,
                DB_NAME
            )

            USE_SQLITE = False

        except Exception as e:

            print('> Error: DBMS Exception: ' + str(e))
            print('> Fallback to SQLite ')

    if USE_SQLITE:
        # This will create a file in <app> FOLDER
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'db.sqlite3')
        
    SENDER_MAIL = os.environ.get('SENDER_MAIL')
    MAILTRAP_API_KEY = os.environ.get('MAILTRAP_API_KEY')
    MAILTRAP_TEMP_UUID = os.getenv("MAILTRAP_TEMP_UUID")
    
    # MAIL_SERVER = os.getenv("MAIL_SERVER")
    # MAIL_PORT = os.getenv("MAIL_PORT")
    # MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    # MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    # MAIL_USE_TLS = True
    # MAIL_USE_SSL = False
    
    NYLAS_OAUTH_CLIENT_ID = "d05jow5hd9z0q6dlrmt1w52s9"
    NYLAS_OAUTH_CLIENT_SECRET = "5w3ost6x3aoztwomi10xg8e6g"
    
    JobStore_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'jobs.sqlite3')
    # Background Schedular settins
    SCHEDULER_JOBSTORES = {
        "default": SQLAlchemyJobStore(url=JobStore_DATABASE_URI)
    }
    SCHEDULER_EXECUTORS = {"default": {"type": "threadpool", "max_workers": 5000}}
    SCHEDULER_JOB_DEFAULTS = {"coalesce": False, "max_instances": 5000}
    SCHEDULER_API_ENABLED = True
    

class ProductionConfig(Config):
    DEBUG = False

    # Security
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = 3600


class DebugConfig(Config):
    DEBUG = True
    REMEMBER_COOKIE_DURATION = timedelta(days=1)


# Load all possible configurations
config_dict = {
    'Production': ProductionConfig,
    'Debug': DebugConfig
}

API_GENERATOR = {
    "filters": "Filter",
    "facebook_accounts": "FacebookAccount",
}
