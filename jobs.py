from apps import scheduler, db
from flask_login import current_user
from apps.models import Email, Automation, Action, Template

    
def email_automation_job(actionid, jobid):
    
    with scheduler.app.app_context():
        
        print(Automation.query.all())
        
    print("Email Automation", actionid, jobid)