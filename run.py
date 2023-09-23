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
from flask_socketio import SocketIO, send, emit
from api_generator.commands import gen_api
from flask_cors import CORS
from apps.config import config_dict
from apps import create_app, db
from apps.models import Service, Yelpurl
from apps.authentication.models import Users
from dotenv import load_dotenv
import mailtrap as mt

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
Migrate(app, db)

if not DEBUG:
    Minify(app=app, html=True, js=False, cssless=False)

# if DEBUG:
#     app.logger.info('DEBUG            = ' + str(DEBUG))
#     app.logger.info('Page Compression = ' + 'FALSE' if DEBUG else 'TRUE')
#     app.logger.info('DBMS             = ' + app_config.SQLALCHEMY_DATABASE_URI)
#     app.logger.info('ASSETS_ROOT      = ' + app_config.ASSETS_ROOT)

for command in [gen_api, ]:
    app.cli.add_command(command)

socketio = SocketIO(app)
CORS(app)


@socketio.on('message')
def handle_message(data):
    message = data['message']
    send({'message': message}, broadcast=True)


@app.route('/msg', methods=['POST'])
def msg1():
    data = request.json['result']
    if data == "completed":
        socketio.emit('message', {'message': "completed"})
        #Send email here
        user_id = request.json['user_id']
        url_id = request.json['id']
        user = Users.query.get(int(user_id))
        user_email = user.email
        print("Send email here", user_email, app.config['SENDER_MAIL'])
        send_email(app.config['SENDER_MAIL'], user_email, url_id)
        s="completed"
    else:
        try:
            # yelpurl = Yelpurl.query.get(int(data['url_id']))
            # s = yelpurl.state
            # if s == "completed":
            #     #Send email here
            #     user = Users.query.get(int(data['user_id']))
            #     user_email = user.email
            #     print("Send email here", user_email, app_config['SENDER_MAIL'])
            #     send_email(app_config['SENDER_MAIL'], user_email)
            #     return s
            
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
        socketio.emit('message', {'message': data})
        yelpurl = Yelpurl.query.get(int(data['url_id']))
        s = yelpurl.state
    return s

def send_email(sender_email, receiver_email, url_id):
    # create mail object
    view_data_link = app.config['WEB_HOST_IP'] + "/url/view/" + str(url_id)
    mail = mt.Mail(
        sender=mt.Address(email=sender_email, name="Robotic Booking Agent"),
        to=[mt.Address(email=receiver_email)],
        template_uuid="eba046d2-f2d5-490c-9b87-7c5ecf558925",
        template_variables={
        "view_data_link": view_data_link,
        "user_email": "Test_User_email",
        "pass_reset_link": "Test_Pass_reset_link"
        }
    )

    # create client and send
    try:
        client = mt.MailtrapClient(token=app.config['MAILTRAP_API_KEY'])
        client.send(mail)
    except Exception as e:
        print(str(e))

if __name__ == "__main__":
    socketio.run(app, debug=True, host='0.0.0.0', port=8081)
    # socketio.run(app, debug=True, host='0.0.0.0', port=80)
