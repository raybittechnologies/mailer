# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

import os
from flask import request
from flask_login import current_user
from flask_migrate import Migrate
from flask_minify import Minify
from sys import exit
# from flask_socketio import SocketIO, send, emit
from api_generator.commands import gen_api
from flask_cors import CORS
from apps.config import config_dict
from apps import create_app, db
from apps.models import Service, Yelpurl
from apps.authentication.models import Users
from apps.home.emailler import send_email
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

# WARNING: Don't run with debug turned on in production!
DEBUG = (os.getenv('DEBUG', 'False') == 'True')

# The configuration
get_config_mode = 'Debug' if DEBUG else 'Production'

try:
    # Load the configuration using the default values
    app_config = config_dict[get_config_mode]

except KeyError:
    exit('Error: Invalid <config_mode>. Expected values [Debug, Production] ')
app = create_app(app_config)
Migrate(app, db, render_as_batch=True)

if not DEBUG:
    Minify(app=app, html=True, js=False, cssless=False)

# if DEBUG:
#     app.logger.info('DEBUG            = ' + str(DEBUG))
#     app.logger.info('Page Compression = ' + 'FALSE' if DEBUG else 'TRUE')
#     app.logger.info('DBMS             = ' + app_config.SQLALCHEMY_DATABASE_URI)
#     app.logger.info('ASSETS_ROOT      = ' + app_config.ASSETS_ROOT)

for command in [gen_api, ]:
    app.cli.add_command(command)

# socketio = SocketIO(app)
CORS(app)

app.wsgi_app = ProxyFix(app.wsgi_app)

@app.route('/msg', methods=['POST'])
def msg1():
    data = request.json['result']
    if data == "completed":
        #Send email here
        user_id = request.json['user_id']
        url_id = request.json['id']
        user = Users.query.get(int(user_id))
        user_email = user.email
        user_name = user.username
        
        SENDER_MAIL = os.environ.get('SENDER_MAIL')
        print("Send email to", user_email, "from", SENDER_MAIL)
        try:
            send_email(user_email, SENDER_MAIL, url_id, user_name)
        except Exception as e:
            with open("send_email_logs.log", "w") as f:
                f.write(repr(e))
                
        s="completed"
    else:
        try:
            print("=========", data['venue'] if type(data) == 'str' else data['venue'][0],  "=========")
            existing_url = Service.query.filter_by(url_id=data['url_id'], user_id=data['user_id'], biz_id=data['bizId']).first()
            if existing_url is None:
                new_service = Service(
                    name= data['venue'] if type(data) == 'str' else data['venue'][0],
                    venue_type= data['venuetype'] if type(data) == 'str' else data['venuetype'][0],
                    website=data['website'],
                    phone=data['Phone'],
                    address=data['address'],
                    facebook=data['facebook'],
                    instagram=data['instagram'],
                    twitter=data['twitter'],
                    email1=data['Email1'],
                    email2=data['Email2'],
                    email3=data['Email3'],
                    email4=data['Email4'],
                    fbemail1=data['FacebookEmail1'],
                    fbemail2=data['FacebookEmail2'],
                    url_id=data['url_id'],
                    user_id=data['user_id'],
                    biz_id=data['bizId']
                )
                db.session.add(new_service)
                db.session.commit()
            else:
                print("Already present in db")
        except Exception as e:
            print("Not Saved in db", str(e))
        yelpurl = Yelpurl.query.get(int(data['url_id']))
        s = yelpurl.state
    return s

if __name__ == "__main__":
    # socketio.run(app, debug=True, host='0.0.0.0', port=8081)
    # socketio.run(app, debug=True, host='0.0.0.0', port=80)
    app.run(debug=True, host='0.0.0.0', port=8081)
