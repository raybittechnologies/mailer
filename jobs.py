import time
from apps import scheduler, db
from flask_login import current_user
from apps.models import Email, Automation, Action, Template, Uploadedservice
from apps.home.emailler import send_email_via_nylas
from nylas import APIClient
from jinja2 import Template as JT
import os
    
def email_automation_job(nylas_token, actionid, jobid, useremail):
    
    with scheduler.app.app_context():
        print("Automation job started", jobid)
        
        client = APIClient(
                client_id=scheduler.app.config["NYLAS_OAUTH_CLIENT_ID"],
                client_secret=scheduler.app.config["NYLAS_OAUTH_CLIENT_SECRET"],
                access_token=nylas_token
            )
        
        action = Action.query.filter_by(id=actionid).first()
        subject = action.subject
        fromname = action.fromname
        message = action.message
        jinja_temp = JT(message)
        
        emails = Email.query.filter_by(job_id=jobid).all()
        WEB_HOST_IP = os.environ.get('WEB_HOST_IP')
        
        job = Automation.query.filter_by(job_id=jobid).first()
        
        if job is None:
            return
        
        # Indicate job is running
        job.status = "running"
        db.session.commit()
        
        for email in emails:
            
            if email.is_unsubscribed == 1:
                continue
            
            print(email.email)
            
            unsubscribe_link = WEB_HOST_IP + "/unsubscribe/" + email.unsubscribe_token
            serv = Uploadedservice.query.filter_by(unsubscribe_token=email.unsubscribe_token).first()
            
            if serv is None:
                continue
            
            venue = serv.name
            service = {
                "venue" : venue,
                "unsubscribe_link" : unsubscribe_link
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
                    else:
                        break
            
            if is_sent:
                email.is_sent = 1
                message_id = response['id']
                email.mail_id = message_id
                
                # Refer this https://developer.nylas.com/docs/email/improving-email-delivery/
                time.sleep(30)
                
            db.session.commit()
        
        # Indicate job is finished
        job.status = "completed"
        db.session.commit()
        
        