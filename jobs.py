import time
import requests
from apps.authentication.util import generate_job_id
from apps import scheduler, db
from apps.models import Email, Automation, Action,Mailing, Template, Uploadedservice, UserCredit, Service, PushNotificationInfo, Reminder
from apps.authentication.models import Users
from apps.home.emailler import send_email_via_nylas,send_email_via_unimail, send_reconnect_email_via_mailtrap, send_email_via_mailtrap
from nylas import Client
from jinja2 import Template as JT
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import pytz
from apps.home.utils import send_push_notification
import urllib.parse
from flask import current_app, jsonify
from sqlalchemy import func
from sqlalchemy import or_ , and_
from random import randint
from math import ceil

load_dotenv()

NYLAS_API_KEY = os.getenv('NYLAS_API_KEY')
NYLAS_API_URI = os.getenv('NYLAS_API_URI')

nylas = Client(
    api_key = NYLAS_API_KEY,
    api_uri = NYLAS_API_URI,
)


def email_automation_job(nylas_client, actionid, jobid, useremail,userId):
    print("?? email_automation_job STARTED:", jobid)
    print("Automation job started")
    with scheduler.app.app_context():
        print("Automation job started", jobid)
        
        action = Action.query.filter_by(id=actionid).first()

        if action is None:
            return
        
        subject = action.subject
        fromname = action.fromname
        message = action.message
        
        emails = Email.query.filter_by(job_id=jobid, is_unsubscribed=0).all()

        WEB_HOST_IP = os.getenv('WEB_HOST_IP')
        
        job = Automation.query.filter_by(job_id=jobid).first()
        
        if job is None:
            return

        try:
            jinja_temp = JT(message)
        except:
            job.status = "failed"
            job.subject = "There is an issue in message"
            db.session.commit()
            return
        
        # Indicate job is running
        job.status = "running"
        db.session.commit()
        emails_count = len(emails)

        if emails_count == 0:
            job.status = "completed"
            print(jobid, "Emails count", len(emails))
            db.session.commit()
            return

        total_minutes_of_a_day = 24 * 60
        minutes_per_email = total_minutes_of_a_day // emails_count
        wait_seconds = minutes_per_email * 60

        job_status = "completed"
        
        for idx, email in enumerate(emails):

            # Check current user is approved or not
            user = db.session.get(Users, int(action.userid))
            if user and user.state == 'pending':
                break
            
            if user is None: # User is deleted
                break

            if job.status == "stopped":
                job_status = "stopped"
                break

            try:
                if email.is_unsubscribed == 1 or email.is_sent == 1: # if email is unsubscribed or sent, skip
                    continue
            except Exception as e:
                print("Failed to check is_unsubscribed: ", email.email,  str(e))
                continue

            # if email is sent, skip : in case for resuming the job after stopping
            try:
                if email.is_sent == 1:
                    continue
            except Exception as e:
                print("Failed to check is_sent: ", email.email, str(e))
                continue

            unsubscribe_token = email.unsubscribe_token
            reciver = Uploadedservice.query.filter_by(unsubscribe_token=unsubscribe_token).first()
            if reciver is None:
                print("No reciver email found")
                continue
            
            reciver_email = reciver.email # need to use this email from uploaded service because email might be changed in email table by user

            print("Sending to", reciver_email)
            
            unsubscribe_link = WEB_HOST_IP + "/unsubscribe/choose?token=" + str(unsubscribe_token) + "&_id=" + str(action.userid)
            # serv = Uploadedservice.query.filter_by(unsubscribe_token=email.unsubscribe_token).first()
            
            # if serv is None:
            #     continue

            if email.email.lower() != reciver_email.lower():
                # update email in email table
                email.email = reciver_email
                db.session.commit()
            
            venue = email.venue
            firstname = email.firstname if email.firstname and email.firstname != "None" else ""
            customtext = email.customtext
            originalemail = email.originalemail

            service = {
                "venue": venue,
                "unsubscribe_link": unsubscribe_link,
                "firstname": firstname,
                "customtext": customtext if customtext else "",
                "originalemail": originalemail if originalemail else ""
            }
            try:
                mail_body = jinja_temp.render(service)
            except Exception as e:
                print("Failed rendering jinja template:", str(e))
                continue
            
            is_sent = False
            while True:
                try:
                    mailings=Mailing.query.filter_by(user_id=userId).first()
                    if mailings:
                        print("Unimail---")
                        response = send_email_via_unimail(mailings, subject, venue, useremail, fromname, mail_body, reciver_email, 'grant_id')
                    else:
                        print("Nylas---")
                        grant_id = user.nylas_access_token
                        print("Grant ID:", grant_id)
                        if grant_id is None:
                            job.status = "failed"
                            subject = "Campaign Failed - Please re-connect Email EMAIL"
                            fromname = "Robotic Booking Agent"
                            send_reconnect_email_via_mailtrap(subject, fromname, useremail)
                            db.session.commit()
                            return
                        response = send_email_via_nylas(nylas_client, subject, venue, useremail, fromname, mail_body, reciver_email, grant_id)
                        
                    if response:
                        is_sent = True
                    else:
                        is_sent = False
                    break
                except Exception as e:
                    print("Failed", str(e))
                    
                    if "No Grant found for this Grant ID." in str(e) or "Grant not found for given ID/Email" in str(e) or 'expired' in str(e).lower():
                        job.status = "failed"
                        subject = "Campaign Failed - Please re-connect Email EMAIL"
                        fromname = "Robotic Booking Agent"
                        
                        send_reconnect_email_via_mailtrap(subject, fromname, useremail)

                        # delete user nylas token
                        user = db.session.get(Users, int(action.userid))
                        user.nylas_access_token = None
                        db.session.commit()
                        
                        return
                    
                    else:
                        time.sleep(5)
                        break
            print(is_sent)
            if is_sent:
                email.is_sent = 1

                message_id = response.data.id
                    
                email.mail_id = message_id
                
                db.session.commit()
                
            if idx + 1 == emails_count:
                break
            else:
                time.sleep(wait_seconds)
                # time.sleep(30) # for testing

        # Indicate job is finished
        try:
            job.status = job_status
            db.session.commit()
        except Exception as e:
            print("Failed to commit db session:", str(e))


def job_manage_credit():
    print("Daily job started", datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f"))
    with scheduler.app.app_context():
        user_credits = UserCredit.query.all()

        for user_credit in user_credits:
            cur_datetime = datetime.utcnow()
            last_updated = user_credit.update_datetime
            montly_credit = user_credit.monthly_credit
            diff = (cur_datetime + timedelta(minutes=1)) - last_updated # it might be run earlier a few milliseconds so added 1 minute margin
            days = diff.days    

            if int(days) == 30: # 30 days
                user_credit.credit += montly_credit

        db.session.commit()


def job_push_notification_reminder(job_id, user_id):
    print("Push notification job started", datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f"))
    with scheduler.app.app_context():

        push_infos = PushNotificationInfo.query.filter_by(userid=user_id).all()
        for push_notify_info in push_infos:
            sub_info = push_notify_info.subscription_info
            reminder = Reminder.query.filter_by(job_id=job_id).first()

            if reminder is None:
                continue

            reminder_email = reminder.email
            user_id = reminder.userid

            upload_service = Uploadedservice.query.filter_by(email=reminder_email, user_id=user_id).first()
            if upload_service is None:
                # delete reminder
                Reminder.query.filter_by(job_id=job_id).delete()
                db.session.commit()
                continue
            
            title = reminder.title
            body = reminder.note
            reminder_id = reminder.id
            
            endpoint_url = sub_info.get('endpoint')
            parsed_url = urllib.parse.urlparse(endpoint_url)
            origin = f"{parsed_url.scheme}://{parsed_url.netloc}"

            vapid_claims = scheduler.app.config['VAPID_CLAIMS']
            vapid_claims.update({'aud' : origin})
            vapid_private_key = scheduler.app.config['VAPID_PRIVATE_KEY']
            url = f"/reminders?reminder_id={reminder_id}"

            print("Sending", reminder_email, user_id)
            send_push_notification(sub_info, title,  body, reminder_id, vapid_claims, vapid_private_key, url)


def job_send_weekly_reminding_past_reminder_email():

    with scheduler.app.app_context():
        print("Weekly reminder job started", datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f"))
        current_time = datetime.utcnow()

        #  get all reminders whith status active and reminder_time < current_time and group by user_id
        reminders = (
                    Reminder.query
                    .with_entities(Reminder.userid, func.min(Reminder.reminder_time).label('reminder_time'))
                    .filter(Reminder.status == 'active', Reminder.reminder_time < current_time)
                    .group_by(Reminder.userid)
                    .all()
                )

        print("Reminders count", len(reminders))
        for reminder in reminders:
            user_id = reminder.userid
            user = db.session.get(Users, user_id)
            if user is None:
                # delete reminders
                Reminder.query.filter_by(userid=user_id).delete()
                db.session.commit()
                continue

            if user.state == 'pending':
                continue

            user_email = user.email

            subject = "PAST due reminders on Robotic Booking Agent"
            fromname = "Robotic Booking Agent"
            # "Hi,
            #     This is a friendly reminder you have active "past due" reminders on Robotic Booking Agent that are requiring your attention.
            #     Please login so you can view them to follow up with your hot leads. 
            #     https://www.roboticbookingagent.com/
            #     You're soo close to securing that gig; Don't let this fall through the cracks!
            #     Please note: you will keep getting this reminder every week if you have any "past due" reminders. So make sure to change them to the future to prevent this reminder from being emailed to you weekly. You can also unsubscribe from these reminder emails using the link below.
            #     Sincerely, 
            #     Team Soundheart Music (Robotic Booking Agent)
            #     (Unsubscribe from weekly reminder emails link) 
            body = f"""
                <p>Hi,</p>
                <p>This is a friendly reminder you have active "past due" reminders on Robotic Booking Agent that are requiring your attention.</p>
                <p>Please login so you can view them to follow up with your hot leads.</p>
                <p><a href="https://roboticbookingagent.com/reminders">https://roboticbookingagent.com/</a></p>
                <p>You're soo close to securing that gig; Don't let this fall through the cracks!</p>
                <p>Please note: you will keep getting this reminder every week if you have any "past due" reminders. So make sure to change them to the future to prevent this reminder from being emailed to you weekly. You can also unsubscribe from these reminder emails using the link below.</p>
                <p>Sincerely,</p>
                <p>Team Soundheart Music (Robotic Booking Agent)</p>
            """
            receiver = user_email
            response = send_email_via_mailtrap(subject, fromname, body, receiver)

def job_email_tracking():
    with scheduler.app.app_context():
        url = "https://beunimailer.roboticbookingagent.com"
        
        s_emails = Email.query.filter(
            Email.is_sent == 1,
            Email.is_archived == 0,
            Email.is_unsubscribed == 0,
            Email.updated_datetime >= (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1))
        ).all()
   

        for email in s_emails:
            message_id = email.mail_id

            if message_id:
                response = requests.get(f"{url}/email-status/{message_id}")

                if response.status_code == 200:
                    data = response.json()['data']['status']

                    if data['is_replied'] == 1:
                        print("Email replied", email.email, message_id)
                        email.is_replied = 1
                        
                        service = Uploadedservice.query.filter_by(unsubscribe_token=email.unsubscribe_token).first()
                        # unsubscribe the email
                        if service is None:
                            print("No service found")
                            return "OK"
                        
                        # Get user id
                        user_id = service.user_id
                        user = Users.query.get(user_id)

                        if user.is_auto_unsub:
                            service.is_unsubscribed = 1
                        
                            # update associated email
                            emails = Email.query.filter_by(unsubscribe_token=email.unsubscribe_token).all()
                            for email in emails:
                                email.is_unsubscribed = 1
                                
                            service = Uploadedservice.query.filter_by(unsubscribe_token=email.unsubscribe_token).first()
                            
                            # unsubscribe all emails from this business : same business
                            if service:
                                service.is_unsubscribed = 1
                                address = service.address
                                biz_id = service.biz_id

                                if biz_id:
                                    # Unsubscribe all emails from this business : same business
                                    services = Uploadedservice.query.filter_by(user_id = user_id, biz_id=biz_id).all()
                                    for service in services:
                                        # Unsubscribe all service with this business
                                        service.is_unsubscribed = 1
                                        
                                        # Unsubscribe all emails from campaigns
                                        unsubscribe_token = service.unsubscribe_token
                                        email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                                        if email:
                                            print("unsubscribed", email.email)
                                            email.is_unsubscribed = 1
                                        
                                elif address:
                                    # Unsubscribe all emails from this address : same business
                                    services = Uploadedservice.query.filter_by(user_id = user_id, address=address).all()
                                    for service in services:
                                        # Unsubscribe all service with this address
                                        service.is_unsubscribed = 1
                                        
                                        # Unsubscribe all emails from campaigns
                                        unsubscribe_token = service.unsubscribe_token
                                        email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                                        if email:
                                            print("unsubscribed", email.email)
                                            email.is_unsubscribed = 1

                                else:
                                    phone = service.phone
                                    if phone:
                                        # Unsubscribe all emails from this phone : same business
                                        services = Uploadedservice.query.filter_by(user_id = user_id, phone=phone).all()
                                        for service in services:
                                            # Unsubscribe all service with this phone
                                            service.is_unsubscribed = 1
                                            
                                            # Unsubscribe all emails from campaigns
                                            unsubscribe_token = service.unsubscribe_token
                                            email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                                            if email:
                                                print("unsubscribed", email.email)
                                                email.is_unsubscribed = 1
                                            
                                    else:
                                        venue = service.name
                                        if venue:
                                            # Unsubscribe all emails from this venue : same business
                                            services = Uploadedservice.query.filter_by(user_id = user_id, name=venue).all()
                                            for service in services:
                                                # Unsubscribe all service with this venue
                                                service.is_unsubscribed = 1
                                                
                                                # Unsubscribe all emails from campaigns
                                                unsubscribe_token = service.unsubscribe_token
                                                email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                                                if email:
                                                    print("unsubscribed", email.email)
                                                    email.is_unsubscribed = 1

                                                
                        user_id = service.user_id

                        # Create reminder after 7 days at 2pm
                        current_time = datetime.datetime.now() # RBS Server time is UTC timezone
                        utc_time = pytz.utc.localize(current_time)
                        est = pytz.timezone('US/Eastern')
                        est_time = utc_time.astimezone(est)
                        reminder_est_time = est_time + timedelta(days=7) 
                        reminder_est_time = reminder_est_time.replace(hour=14, minute=0, second=0)

                        # convert est time to utc time
                        reminder_utc_time = reminder_est_time.astimezone(pytz.utc)
                        utc_time_iso_string = reminder_utc_time.strftime('%Y-%m-%d %H:%M:%S')

                        reminder = Reminder.query.filter_by(userid=user_id, email=email.email).first()

                        if reminder:
                            job_id = reminder.job_id
                            if scheduler.get_job(job_id):
                                scheduler.remove_job(job_id)

                            db.session.delete(reminder)
                        
                        job_id = "job_" + generate_job_id(32)
                        job = {
                            "id" : job_id,
                            'trigger' : 'date',
                            "run_date" : utc_time_iso_string,
                            "func" : "jobs:job_push_notification_reminder",
                            "args" : (job_id, user_id)
                        }
                        try:
                            scheduler.add_job(**job) # TODO: Uncomment this line
                            print("Auto created job for reminder", job_id)
                        except Exception as e:
                            print("Failed to create job", str(e))
                            return {"success": False, "message": "Something went wrong. Please try again."}
                        
                        reminder_template = "Follow up w/ [name] @ [venue] **See email from [email] [phone]"
                        reminder = Reminder()
                        reminder.job_id = job_id
                        reminder.note = ''
                        reminder.name = service.firstname
                        reminder.email = email.email
                        reminder.phone = service.phone
                        reminder.venue = service.name
                        reminder.title = f"Follow up w/ {service.firstname} @ {service.name} **See email from {email.email} {service.phone}"
                        reminder.note_template = reminder_template
                        reminder.reminder_time = utc_time_iso_string  
                        reminder.status = "active"
                        reminder.userid = user_id
                        db.session.add(reminder)
                        db.session.commit()

                    email.is_opened = data['is_opened']

                    if data['is_bounced'] == 1:
                        # unsubscribe the email
                        unsub_token = email.unsubscribe_token
                        if unsub_token:
                            emails = Email.query.filter_by(unsubscribe_token=unsub_token).all()
                            for email in emails:
                                email.is_unsubscribed = 1
                                email.is_bounced = 1
                            
                            service = Uploadedservice.query.filter_by(unsubscribe_token=unsub_token).first()
                            if service:
                                service.is_unsubscribed = 1
                                service.is_bad = 1

        db.session.commit()

def job_check_automation_status():
    with scheduler.app.app_context():
        # Check and create a job for stucked ones which are not running, and join user data by userid
        records = db.session.query(Automation, Users, Action).join(Users, Automation.userid == Users.id).join(Action, Automation.action_id == Action.id).filter(
            or_(Automation.status == 'pending', Automation.status == 'running'),
            or_(Automation.is_archived == False, Automation.is_archived == None),
        ).all()

        print("Records count", len(records))
        print("Started at", datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f"))

        for record in records:
            automation = record.Automation
            action = record.Action
            user = record.Users

            if automation.action_datetime <= datetime.now(timezone.utc).replace(tzinfo=None):
                delta = randint(60, 7200)
                job_starttime = datetime.now() + timedelta(seconds=delta)
                job_start_utctime = datetime.now(timezone.utc) + timedelta(seconds=delta)
                automation.action_datetime = job_start_utctime
                job = {
                    "id" : automation.job_id,
                    'trigger' : 'date',
                    "run_date" : job_starttime.strftime("%Y-%m-%d %H:%M:%S"),
                    "func" : "jobs:email_automation_job",
                    "args" : (nylas, action.id, automation.job_id, user.email, user.id)
                }

                if scheduler.get_job(automation.job_id):
                    scheduler.remove_job(automation.job_id)

                try:
                    scheduler.add_job(**job) # TODO: Uncomment this line
                    print("Created job ", automation.job_id)

                    automation.status = "pending"
                    automation.action_datetime = job_start_utctime
                except Exception as e:
                    print("Failed to create job", str(e))

        db.session.commit()

def job_send_daily_reminding_campaign_end():
    with scheduler.app.app_context():
        # Calculate time ranges
        current_utctime = datetime.now(timezone.utc).replace(tzinfo=None)

        # Subquery to get latest action_datetime per campaignid
        latest_datetimes_subq = db.session.query(
            Automation.campaignid,
            func.max(Automation.action_datetime).label('latest_datetime')
        ).group_by(Automation.campaignid).subquery()

        # Main query with user email join
        results = db.session.query(
            Automation,
            Users.state.label('user_state'),
            Users.email.label('user_email')
        ).join(
            Users, Automation.userid == Users.id
        ).join(
            latest_datetimes_subq,
            db.and_(
                Automation.campaignid == latest_datetimes_subq.c.campaignid,
                Automation.action_datetime == latest_datetimes_subq.c.latest_datetime
            )
        ).filter(
            Automation.is_archived == 0
        ).all()

        for automation, user_state, user_email in results:
            if user_state == 'pending':
                continue
            
            seconds = (automation.action_datetime - current_utctime).total_seconds()
            hours = int(seconds / 3600)

            subject = "Important: Your campaign is expired"
            fromname = "Robotic Booking Agent"
            body = """
                <p>Hi there,</p>
                <br/>
                %s
                <br/>
                <p>Please login</p>
                <p><a href="https://soundheartmusic.com">soundheartmusic.com</a></p>
                <p>and navigate to "Campaigns" Tab </p>
                <p>While noting the campaigns you already have running, and also the ones launched in the past by clicking the "Archive View" Button</p>
                <p>Click "Create Campaign" button</p>
                <p>Launch a new campaign with no more than 315 emails per week TOTAL (That's GENERALLY 3 batches, some may have less, but you can see how many emails there by clicking the drop down menu, and the number next to the Contact List is the amount per week</p>
                <br/>
                <p>Happy Gig-Hunting!</p>
                <br/>
                <p>Thank you,</p>
                <br/>
                <p>PS - Please contact us if you'd like to add an additional email for your campaign (8 per mo more)</p>
            """
            receiver = user_email
            
            if hours == 0:
                subject = "Important: Your campaign is about to expire"
                body = body % "<p>It's Soundheart Music - Your campaign will be expired in 24 hours, and it's time to start the new ones</p>"
                response = send_email_via_mailtrap(subject, fromname, body, receiver)

            if hours == -24:
                body = body % "<p>It's Soundheart Music - Your campaign is expired just now, and it's time to start the new ones</p>"
                response = send_email_via_mailtrap(subject, fromname, body, receiver)

            if hours == -48:
                body = body % "<p>It's Soundheart Music - Your campaign was expired 24 hours ago, and it's time to start the new ones</p>"
                response = send_email_via_mailtrap(subject, fromname, body, receiver)

            if hours == -60:
                body = body % "<p>It's Soundheart Music - Your campaign was expired 32 hours ago, and it's time to start the new ones</p>"
                response = send_email_via_mailtrap(subject, fromname, body, receiver)

            if hours == -96:
                body = body % "<p>It's Soundheart Music - Your campaign was expired 72 hours ago, and it's time to start the new ones</p>"
                response = send_email_via_mailtrap(subject, fromname, body, receiver)

            if hours < 0 and hours % 168 == 0:
                body = body % f"<p>It's Soundheart Music - Your campaign was expired {int(hours) / 168} weeks ago, and it's time to start the new ones</p>"
                response = send_email_via_mailtrap(subject, fromname, body, receiver)
