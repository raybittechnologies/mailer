import os

import mailtrap as mt
from flask_dance.contrib.nylas import make_nylas_blueprint, nylas
from nylas import APIClient
from flask import current_app
from flask_login import current_user

def send_email(user_email, sender_email, url_id, user_name):
    WEB_HOST_IP = os.environ.get('WEB_HOST_IP')
    MAILTRAP_TEMP_UUID = os.environ.get('MAILTRAP_TEMP_UUID')
    MAILTRAP_API_KEY = os.environ.get('MAILTRAP_API_KEY')
    view_data_link = WEB_HOST_IP + "/url/view/" + str(url_id)
    
    # create mail object
    mail = mt.MailFromTemplate(
        sender=mt.Address(email=sender_email, name="Robotic Booking Agent"),
        to=[mt.Address(email=user_email)],
        template_uuid=MAILTRAP_TEMP_UUID,
        template_variables={
        "view_data_link": view_data_link,
        "user_email": user_email,
        "user_name" : user_name
        }
    )

    # create client and send
    client = mt.MailtrapClient(token=MAILTRAP_API_KEY)
    client.send(mail)


def send_test_email(subject, fromname, body, receiver, sender):
    
    MAILTRAP_API_KEY = os.environ.get('MAILTRAP_API_KEY')
    
    mail = mt.Mail(
        sender=mt.Address(email=sender, name=fromname),
        to=[mt.Address(email=receiver, name="Admin")],
        subject=subject,
        text="This is for Test for mail merge!",
        
        html=f"""
            <!doctype html>
            <html>
            <head>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
            </head>
            <body style="font-family: sans-serif;">
                {body}
            </body>
            </html>
        """
    )

    client = mt.MailtrapClient(token=MAILTRAP_API_KEY)
    response = client.send(mail)
    if not response['success']:
        print(response)
        
    return response['success']
    


def user_test_email(subject, fromname, body, receiver):
    
    # print(current_user.nylas_access_token)
        
    client = APIClient(
        client_id=current_app.config["NYLAS_OAUTH_CLIENT_ID"],
        client_secret=current_app.config["NYLAS_OAUTH_CLIENT_SECRET"],
        access_token=current_user.nylas_access_token,
    )

    html=f"""
        <!doctype html>
        <html>
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
        </head>
            <body style="font-family: sans-serif;">
                {body}
            </body>
        </html>
    """
    
    
    message = client.drafts.create()
    message.body = html
    message.to = [{'email': receiver, 'name': fromname}]
    message.tracking = {
        "opens": True, # Enable message open tracking.
        "links": True, # Enable link clicked tracking.
        "thread_replies": True, # Enable thread replied tracking.
        "payload": "Use this string to describe the message you're enabling tracking for. It's included in webhook notifications about tracked events."
    }
    message.subject = subject
    response = message.send()
    
    # print(response)

    # if not response['success']:
    #     print(response)
        
    return True
