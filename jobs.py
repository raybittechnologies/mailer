import time
from apps import scheduler, db
from apps.models import Email, Automation, Action, Template, Uploadedservice, UserCredit, Service, PushNotificationInfo, Reminder
from apps.authentication.models import Users
from apps.home.emailler import send_email_via_nylas, send_reconnect_email_via_mailtrap, send_email_via_mailtrap
from nylas import Client
from jinja2 import Template as JT
import os
from datetime import datetime, timedelta
from apps.home.utils import send_push_notification
import urllib.parse
from flask import current_app, jsonify
from sqlalchemy import func


def email_automation_job(nylas_client, actionid, jobid, useremail):
    with scheduler.app.app_context():
        print("Automation job started", jobid)
        
        action = Action.query.filter_by(id=actionid).first()

        if action is None:
            return
        
        subject = action.subject
        fromname = action.fromname
        message = action.message
        jinja_temp = JT(message)
        
        emails = Email.query.filter_by(job_id=jobid, is_unsubscribed=0).all()

        WEB_HOST_IP = os.getenv('WEB_HOST_IP')
        
        job = Automation.query.filter_by(job_id=jobid).first()
        
        if job is None:
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
                if email.is_unsubscribed == 1:
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
                return
            
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

            grant_id = user.nylas_access_token

            print("Grant ID:", grant_id)

            if grant_id is None:
                job.status = "failed"
                subject = "Campaign Failed - Please re-connect Email EMAIL"
                fromname = "Robotic Booking Agent"
                send_reconnect_email_via_mailtrap(subject, fromname, useremail)

                db.session.commit()

                return

            while True:
                try:
                    response = send_email_via_nylas(nylas_client, subject, venue, useremail, fromname, mail_body, reciver_email, grant_id)
                    is_sent = True
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




