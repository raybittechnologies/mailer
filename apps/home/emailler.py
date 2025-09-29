import os
from types import SimpleNamespace

import mailtrap as mt
# from flask import current_app
# from flask_login import current_user
from nylas import Client
from dotenv import load_dotenv
load_dotenv()
import requests
import uuid
from flask import request

NYLAS_API_KEY = os.getenv('NYLAS_API_KEY')
NYLAS_API_URI = os.getenv('NYLAS_API_URI')

nylas = Client(
    api_key = NYLAS_API_KEY,
    api_uri = NYLAS_API_URI,
)


def send_email(user_email, sender_email, url_id, user_name):
    WEB_HOST_IP = os.getenv('WEB_HOST_IP')
    MAILTRAP_TEMP_UUID = os.getenv('MAILTRAP_TEMP_UUID')
    MAILTRAP_API_KEY = os.getenv('MAILTRAP_API_KEY')
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
    response = client.send(mail)
    if not response['success']:
        print(response)
        
    return response['success']


def send_cancel_membership_email(user_email):
    MAILTRAP_API_KEY = os.getenv('MAILTRAP_API_KEY')
    SENDER_MAIL = os.getenv('SENDER_MAIL')

    # create mail object
    mail = mt.Mail(
        sender=mt.Address(email=SENDER_MAIL),
        to=[mt.Address(email=SENDER_MAIL, name="Admin")],
        subject="Request for Membership Cancellation",
        html=f"""
            <!doctype html>
            <html>
            <head>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
                <style> p {{
                    font-size: 14px;
                    margin: 5px 0;
                    line-height: 1.5;
                    }}
                </style>
            </head>
            <body style="font-family: sans-serif;">
                <p>Request for Membership Cancellation</p>
                <p>User Email: {user_email}</p>
            </body>
            </html>
        """
    )

    # create client and send
    client = mt.MailtrapClient(token=MAILTRAP_API_KEY)
    response = client.send(mail)
    if not response['success']:
        print(response)
        
    return response['success']


def send_test_email(subject, fromname, body, receiver, sender):
    
    MAILTRAP_API_KEY = os.getenv('MAILTRAP_API_KEY')
    
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
                <style> p {{
                    font-size: 14px;
                    margin: 5px 0;
                    line-height: 1.5;
                    }}
                </style>
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


def send_email_via_mailtrap(subject, fromname, body, receiver):
    WEB_HOST_IP = os.getenv('WEB_HOST_IP')
    SENDER_MAIL = os.getenv('SENDER_MAIL')
    MAILTRAP_API_KEY = os.getenv('MAILTRAP_API_KEY')
    
    mail = mt.Mail(
        sender=mt.Address(email=SENDER_MAIL, name=fromname),
        to=[mt.Address(email=receiver, name="")],
        subject=subject,
        html=f"""
            <!doctype html>
            <html>
            <head>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
                <style> p {{
                    font-size: 14px;
                    margin: 5px 0;
                    line-height: 1.5;
                    }}
                </style>
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

def send_reconnect_email_via_mailtrap(subject, fromname, receiver):
    WEB_HOST_IP = os.getenv('WEB_HOST_IP')
    SENDER_MAIL = os.getenv('SENDER_MAIL')
    MAILTRAP_API_KEY = os.getenv('MAILTRAP_API_KEY')

    message = f"""    
            <p>Hi,</p>

            <p>The mailing robot was unable to send out your campaign just now. No need to worry, as this could happen for various reasons.</p>

            <p>Please reconnect your email by going to: :</p>
            
            <p>
                <a href="{WEB_HOST_IP}/connect_email" style="color: #1a73e8; text-decoration: none;">Connect Email</a>
            </p>
            
            <p>After that, please visit campaign page and click <strong> RETRY </strong>. your campaign will automatically restart where it left off, and any future scheduled e-mails will update their sends with a new updated schedule according to our best practices.</p>
            
            <p>Sorry for any inconvenience this may have caused.</p>
            
            <p>Thank you,</p>
            
            <p>Soundheart team (Robotic Booking Agent)</p>"""
    
    
    mail = mt.Mail(
        sender=mt.Address(email=SENDER_MAIL, name=fromname),
        to=[mt.Address(email=receiver, name="")],
        subject=subject,
        html=f"""
            <!doctype html>
            <html>
            <head>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
                <style> p {{
                    font-size: 14px;
                    margin: 5px 0;
                    line-height: 1.5;
                    }}
                </style>
            </head>
            <body style="font-family: sans-serif;">
                {message}
            </body>
            </html>
        """
    )

    client = mt.MailtrapClient(token=MAILTRAP_API_KEY)
    response = client.send(mail)
    if not response['success']:
        print(response)
        
    return response['success']  


def send_email_via_nylas(nylas, subject, toname, fromemail, fromname, body, receiver, grant_id):
    html=f"""
        <!doctype html>
        <html>
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
            <style> p {{
                    font-size: 14px;
                    margin: 5px 0;
                    line-height: 1.5;
                }}
            </style>
        </head>
            <body style="font-family: sans-serif;">
            {body}
            </body>
        </html>
    """
    message = nylas.messages.send(
        grant_id,
        request_body={
            "to": [{ "name": toname, "email": receiver }],
            "from": [{ "name": fromname, "email": fromemail }],
            "subject": subject,
            "body": html,
            "tracking_options": {
                "opens": True,
                "links": True,
                "thread_replies": True,
                "label": "Use this string to describe the message you're enabling tracking for. It's included in notifications about tracked events."
            }
        }
        )
    # print(message.data)
    return message

def send_email_via_unimail(mailings, subject, toname, fromemail, fromname, body, receiver, grant_id):
    message_id = str(uuid.uuid4())
    html=f"""
        <!doctype html>
        <html>
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
            <style> p {{
                    line-height: 1.5;
                    margin-bottom: -14px;
                    font-size: 16px;
                }}
            </style>
        </head>
            <body style="font-family: sans-serif;">
            <img src="https://beunimail.raybitprojects.com/open/{message_id}" style="display:none;" width="1" height="1"/>
            {body}
            </body>
        </html>
    """
    url = "https://beunimail.raybitprojects.com/send-email"
    payload = {
        "id": mailings.user_id,
        "to": receiver,
        "subject": subject,
        "message": html,
        "message_id":message_id
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        json_data = response.json()

        # Wrap into objects for dot notation
        data_obj = SimpleNamespace(id=message_id,mailData=json_data.get("data", ""))
        response_obj = SimpleNamespace(
            success=json_data.get("success", False),
            message=json_data.get("message", ""),
            data=data_obj
        )
        print (response_obj)
        return response_obj
    except requests.exceptions.RequestException as e:
        print(f"Failed to send email: {e}")
        return None

def send_password_reset_email(email, reset_link):
    
    SENDER_MAIL = os.getenv('SENDER_MAIL')
    MAILTRAP_API_KEY = os.getenv('MAILTRAP_API_KEY')
    
    mail = mt.Mail(
        sender=mt.Address(email=SENDER_MAIL, name="Robitic Booking Agent"),
        to=[mt.Address(email=email, name="")],
        subject="Reset your password",
        html=f"""
            <!doctype html>
            <html>
            <head>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
                <style> p {{
                    font-size: 14px;
                    margin: 5px 0;
                    line-height: 1.5;
                    }}
                </style>
            </head>
            <body style="font-family: sans-serif;">
                please click the link below to reset your password.
                {reset_link}
            </body>
            </html>
        """
    )

    client = mt.MailtrapClient(token=MAILTRAP_API_KEY)
    response = client.send(mail)
    if not response['success']:
        print(response)
        
    return response['success']  
