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
from api_generator.commands import gen_api
from flask_cors import CORS
from apps.config import config_dict
from apps import create_app, db, scheduler, csrf
from apps.models import Service, Yelpurl, FirstName
from apps.authentication.models import Users
from apps.home.emailler import send_email
from dotenv import load_dotenv
from apps.home.utils import extract_first_name
from jobs import job_check_automation_status

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
# In order to perform authenticated AJAX queries, the server must specify the header "Access-Control-Allow-
# Credentials: true" and the "Access-Control-Allow-Origin" header must be set to null or the malicious page's domain.
# Even if this misconfiguration doesn't allow authenticated AJAX requests, unauthenticated sensitive content can still
# be accessed (e.g intranet websites).
CORS(app, access_control_allow_origin=None, access_control_allow_credentials=True)
# CORS(app)

# When using Ngrok, uncomment the following lines
# app.wsgi_app = ProxyFix(app.wsgi_app)

if not scheduler.running: # Clause suggested by @CyrilleMODIANO
    scheduler.start()

# User credit job
job_id = 'job_manage_credit'
job = {
        "id" : job_id,
        'trigger' : 'cron',
        'hour' : 0,
        'minute' : 0,
        "func" : "jobs:job_manage_credit",
        "args" : ()
    }

if scheduler.get_job(job_id) is None:
    try:
        scheduler.add_job(**job) # TODO: Uncomment this line
        print("Created Credit job ", job_id)
    except Exception as e:
        print("Failed to create job", str(e))

else:
    print("Credit job already exists")
    try:
        scheduler.remove_job(job_id)
        scheduler.add_job(**job) # TODO: Uncomment this line
        print("Created Credit job ", job_id)
    except Exception as e:
        print("Failed to create job", str(e))

#  Create a job to send email fro users which has past active reminders, start is eveny Monday, 2 pm in local time
remind_job_id = 'job_send_reminder_email_past_due'
job = {
        "id" : remind_job_id,
        'trigger' : 'cron',
        'hour' : 14,
        'minute' : 0,
        'day_of_week' : 'mon', # mon, tue, wed, thu, fri, sat, sun
        "func" : "jobs:job_send_weekly_reminding_past_reminder_email",
        "args" : ()
    }

if scheduler.get_job(remind_job_id) is None:
    try:
        scheduler.add_job(**job) # TODO: Uncomment this line
        print("Created Reminder job ", remind_job_id)
    except Exception as e:
        print("Failed to create job", str(e))

else:
    print("Reminder job already exists")
    try:
        scheduler.remove_job(remind_job_id)
        scheduler.add_job(**job) # TODO: Uncomment this line
        print("Created Reminder job ", remind_job_id)
    except Exception as e:
        print("Failed to create job", str(e))

job_check_automation_status()

@csrf.exempt
@app.route('/msg', methods=['POST'])
def msg1():
    data = request.json['result']
    if data == "completed":
        #Send email here
        user_id = request.json['user_id']
        url_id = request.json['id']
        user = db.session.get(Users, int(user_id))
        user_email = user.email
        user_name = user.email
        
        SENDER_MAIL = os.getenv('SENDER_MAIL')
        print("Send email to", user_email, "from", SENDER_MAIL)
        try:
            send_email(user_email, SENDER_MAIL, url_id, user_name)
        except Exception as e:
            with open("send_email_logs.log", "w") as f:
                f.write(repr(e))
                
        s="completed"
    else:
        try:
            print("=========", data['venue'], "=========")
            existing_url = Service.query.filter_by(url_id=data['url_id'], user_id=data['user_id'], biz_id=data['bizId']).first()

            if existing_url is None:
                user = db.session.get(Users, int(data['user_id']))
                
                emails = [data['Email1'], data['Email2'], data['Email3'], data['Email4'], data['FacebookEmail1'], data['FacebookEmail2']]
                
                # remove duplicates and empty strings
                emails = list(set(filter(None, emails)))
                
                new_service = Service(
                    name= data['venue'],
                    venue_type= data['venuetype'],
                    website=data['website'],
                    phone=data['Phone'],
                    address=data['address'],
                    facebook=data['facebook'],
                    instagram=data['instagram'],
                    twitter=data['twitter'],
                    email1= emails[0] if len(emails) > 0 else '',
                    email2= emails[1] if len(emails) > 1 else '',
                    email3= emails[2] if len(emails) > 2 else '',
                    email4= emails[3] if len(emails) > 3 else '',
                    fbemail1=data['FacebookEmail1'],
                    fbemail2=data['FacebookEmail2'],
                    url_id=data['url_id'],
                    user_id=data['user_id'],
                    biz_id=data['bizId'],
                    city=data['city'],
                    state=data['state'],
                    zip=data['zip'],
                    country=data['country'],
                    latitude=data['latitude'],
                    longitude=data['longitude'],
                    thumnailurl=data['thumnailurl']
                )

                for idx, email in enumerate(emails[:4]):  # Limit to first 4 emails
                    email = str(email).strip()
                    if email:
                        fn = db.session.query(FirstName).filter_by(email=email).first()
                        if fn is None:
                            email_str = email.split('@')[0]
                            first_name = extract_first_name(email_str)
                            
                            venue = data['venue']

                            if first_name != "None" and first_name.lower() in venue.lower(): # Check if first name is in venue name
                                first_name = ""
                            
                            if "none" in first_name.lower():
                                first_name = ""
                            
                            if 'admin' in first_name.lower():
                                first_name = ""
                            
                            if 'info' in first_name.lower():
                                first_name = ""

                            if first_name == "None" or first_name is None:
                                first_name = ""
                                
                            new_first_name = FirstName(
                                email=email,
                                first_name=first_name
                            )

                            db.session.add(new_first_name)
                            db.session.commit()

                        else:
                            first_name = fn.first_name
                            
                        # eben@eyebytes.com & also reject Name Eben along w/ it in the firstname field 
                        # amkryukov@gmail.com & also reject Name amkryukov or amy along w it in the firstname field 
                        # eyebytes.com & also reject Name eyebytes along w it in the firstname field

                        if 'eben' in first_name.lower() or 'amkryukov' in first_name.lower():
                            return ""

                        # add first names to service
                        setattr(new_service, f"first_name{idx+1}", first_name)

                if data['FacebookEmail1']:
                    fn1 = db.session.query(FirstName).filter_by(email=data['FacebookEmail1']).first()
                    if fn1 is None:
                        email_str = data['FacebookEmail1'].split('@')[0]
                        first_name = extract_first_name(email_str)
                        new_first_name = FirstName(
                            email=data['FacebookEmail1'],
                            first_name=first_name
                        )
                        db.session.add(new_first_name)
                        db.session.commit()
                    else:
                        first_name = fn1.first_name
                    new_service.first_name5 = first_name
                
                if data['FacebookEmail2']:
                    fn2 = db.session.query(FirstName).filter_by(email=data['FacebookEmail2']).first()
                    if fn2 is None:
                        email_str = data['FacebookEmail2'].split('@')[0]
                        first_name = extract_first_name(email_str)
                        new_first_name = FirstName(
                            email=data['FacebookEmail2'],
                            first_name=first_name
                        )
                        db.session.add(new_first_name)
                        db.session.commit()
                    else:
                        first_name = fn2.first_name
                    new_service.first_name6 = first_name
                
                db.session.add(new_service)
                db.session.commit()
            else:
                print("Already present in db")
        except Exception as e:
            print("Not Saved in db", str(e))
        # yelpurl = Yelpurl.query.get(int(data['url_id']))
        yelpurl = db.session.get(Yelpurl, int(data['url_id']))
        s = yelpurl.state
    return s

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=8081) # use_reloader=False # for code change detection
