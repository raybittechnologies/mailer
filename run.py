# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

import os
from flask import request, jsonify, render_template
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
import string
import secrets

from apps.authentication.models import Users
from apps.authentication.util import hash_pass
from apps.home.emailler import send_email

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

if DEBUG:
    app.logger.info('DEBUG            = ' + str(DEBUG))
    app.logger.info('Page Compression = ' + 'FALSE' if DEBUG else 'TRUE')
    app.logger.info('DBMS             = ' + app_config.SQLALCHEMY_DATABASE_URI)
    app.logger.info('ASSETS_ROOT      = ' + app_config.ASSETS_ROOT)

for command in [gen_api, ]:
    app.cli.add_command(command)

socketio = SocketIO(app)
CORS(app)


def generate_random_password(length=8):
    # Define the set of characters to choose from
    characters = string.ascii_letters + string.digits + string.punctuation

    # Generate a secure random password
    password = ''.join(secrets.choice(characters) for _ in range(length))

    return password


@socketio.on('message')
def handle_message(data):
    message = data['message']
    send({'message': message}, broadcast=True)


@app.route('/forget_password', methods=['POST', 'GET'])
def check_email():
    if request.method == "POST":
        data = request.form
        email_to_check = data.get('email')

        if not email_to_check:
            response_msg = {
                'class': 'alert-danger',
                'message': 'Email not provided'
            }
        else:
            # Query the database to check if the email exists
            user = Users.query.filter_by(email=email_to_check).first()

            if user:
                try:
                    password = generate_random_password()
                    user.password = hash_pass(password)
                    print(password)
                    db.session.commit()
                    user_email = user.email
                    subject = "Reset password for robotic booking agent"
                    message = "your new password is : " + password
                    resp = send_email(user_email, subject, message)
                    if resp['status'] == 'successful':
                        msg = "Updated Password send to your email"
                        response_msg = {
                            'class': 'alert-success',
                            'message': msg
                        }
                    else:
                        msg = 'something went wrong, Please try again later...'
                        response_msg = {
                            'class': 'alert-danger',
                            'message': msg
                        }
                except Exception as e:
                    response_msg = {
                        'class': 'alert-success',
                        'message': str(e)
                    }
            else:
                response_msg = {
                    'class': 'alert-danger',
                    'message': 'Email not found in the database'
                }
    else:
        response_msg = None
    return render_template('home/forget_password.html', response_msg=response_msg)


@app.route('/msg', methods=['POST'])
def msg1():
    data = request.json['result']
    if data == "completed":
        socketio.emit('message', {'message': "completed"})
        s="completed"
    else:
        print(data)
        try:
            yelpurl = Yelpurl.query.get(int(data['url_id']))
            print(yelpurl.state)
            s = yelpurl.state
            if s == "completed":
                return
            existing_url = Service.query.filter_by(url=data['Url'], user_id=data['url_id']).first()
            if not existing_url:
                new_service = Service(
                    url=data['Url'],
                    name=data['Venue'],
                    venue_type=data['Type'],
                    website=data['website'],
                    phone=data['Phone'],
                    address=data['address'],
                    facebook=data['facebook'],
                    instagram=data['instagram'],
                    twitter=data['twitter'],
                    email=data['email'],
                    url_id=data['url_id'],
                    user_id=data['user_id']
                )
                db.session.add(new_service)
                db.session.commit()
            else:
                print("Already present in db")
        except Exception as e:
            print("Not Saved in db", e)
        socketio.emit('message', {'message': data})
        yelpurl = Yelpurl.query.get(int(data['url_id']))
        print(yelpurl.state)
        s = yelpurl.state
    return s


if __name__ == "__main__":
    socketio.run(app, debug=True, host='0.0.0.0', port=8081)
