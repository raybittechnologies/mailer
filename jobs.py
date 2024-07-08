import time
from apps import scheduler, db
from flask_login import current_user
from apps.models import Email, Automation, Action, Template, Uploadedservice, UserCredit, Service
from apps.home.emailler import send_email_via_nylas, send_email_via_mailtrap
from nylas import APIClient
from jinja2 import Template as JT
import os
from datetime import datetime, timedelta
    
def email_automation_job(nylas_token, actionid, jobid, useremail):
    
    with scheduler.app.app_context():
        print("Automation job started", jobid)
        
        client = APIClient(
                client_id=scheduler.app.config["NYLAS_OAUTH_CLIENT_ID"],
                client_secret=scheduler.app.config["NYLAS_OAUTH_CLIENT_SECRET"],
                access_token=nylas_token
            )
        
        action = Action.query.filter_by(id=actionid).first()

        if action is None:
            return
        
        subject = action.subject
        fromname = action.fromname
        message = action.message
        jinja_temp = JT(message)
        
        emails = Email.query.filter_by(job_id=jobid, is_unsubscribed=0).all()
        WEB_HOST_IP = os.environ.get('WEB_HOST_IP')
        
        job = Automation.query.filter_by(job_id=jobid).first()
        
        if job is None:
            return
        
        # Indicate job is running
        job.status = "running"
        db.session.commit()

        emails_count = len(emails)

        total_minutes_of_a_day = 24 * 60
        minutes_per_email = total_minutes_of_a_day // emails_count
        wait_seconds = minutes_per_email * 60
        
        for email in emails:
            
            # try:
            #     if email.is_unsubscribed == 1:
            #         continue
            # except Exception as e:
            #     print("Failed to check is_unsubscribed: ", email.email,  str(e))
            #     continue

            print("Sending to", email.email)
            
            unsubscribe_link = WEB_HOST_IP + "/unsubscribe/choose?token=" + str(email.unsubscribe_token) + "&_id=" + str(action.userid)
            # serv = Uploadedservice.query.filter_by(unsubscribe_token=email.unsubscribe_token).first()
            
            # if serv is None:
            #     continue
            
            venue = email.venue
            firstname = email.firstname if email.firstname and email.firstname != "None" else ""
            customtext = email.customtext
            originalemail = email.originalemail

            service = {
                "venue" : venue,
                "unsubscribe_link" : unsubscribe_link,
                "firstname" : firstname,
                "customtext" : customtext if customtext else "",
                "originalemail" : originalemail if originalemail else ""
            }
            try:
                mail_body = jinja_temp.render(service)
            except Exception as e:
                print("Failed rendering jinja template:", str(e))
                continue
            
            is_sent = False
            while True:
                try:
                    response = send_email_via_nylas(client, subject, venue, useremail, fromname, mail_body, email.email)
                    is_sent = True
                    break
                except Exception as e:
                    print("Failed", str(e))
                    if "504 Gateway Timeout" in str(e):
                        time.sleep(5)
                        continue
                    
                    if "401" in str(e):
                        job.status = "failed"
                        db.session.commit()
                        subject = "Email Automation Failed"
                        fromname = "Robotic Booking Agent"
                        message = """<p><strong>Email Automation Failed.</strong></p>
                        
                                    <p>Your token is expired.</p>
                                    
                                    <p>Please contact support to reset your token and try again.</p>

                                    <p>Sorry for this inconvenience.</p>

                                    <p>Best regards.</p>"""
                                    
                        send_email_via_mailtrap(subject, fromname, message, useremail)
                        return
                    
                    else:
                        break
            
            if is_sent:
                email.is_sent = 1
                message_id = response['id']
                email.mail_id = message_id
                
                # Refer this https://developer.nylas.com/docs/email/improving-email-delivery/
                time.sleep(wait_seconds)
            
            try:
                db.session.commit()
            except Exception as e:
                print("Failed to commit db session:", str(e))
                continue
        
        # Indicate job is finished
        job.status = "completed"

        try:
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
        