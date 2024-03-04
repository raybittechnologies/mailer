import os

import mailtrap as mt
from flask_dance.contrib.nylas import make_nylas_blueprint, nylas
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
    response = client.send(mail)
    if not response['success']:
        print(response)
        
    return response['success']


def send_cancel_membership_email(user_email):
    MAILTRAP_API_KEY = os.environ.get('MAILTRAP_API_KEY')
    SENDER_MAIL = os.environ.get('SENDER_MAIL')

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


def send_email_via_mailtrap(subject, fromname, body, receiver):
    
    SENDER_MAIL = os.environ.get('SENDER_MAIL')
    MAILTRAP_API_KEY = os.environ.get('MAILTRAP_API_KEY')
    
    mail = mt.Mail(
        sender=mt.Address(email=SENDER_MAIL, name=fromname),
        to=[mt.Address(email=receiver, name="")],
        subject=subject,
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


def send_email_via_nylas(nylas_client, subject, toname, fromemail, fromname, body, receiver):
    
        
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
    message = nylas_client.drafts.create()
    message.body = html
    message.from_ = [{'email': fromemail, 'name': fromname}]
    message.to = [{'email': receiver, 'name': toname}]
    
    message.tracking = {
        "opens": True, # Enable message open tracking.
        "links": True, # Enable link clicked tracking.
        "thread_replies": True, # Enable thread replied tracking.
        "payload": "Use this string to describe the message you're enabling tracking for. It's included in webhook notifications about tracked events."
    }
    message.subject = subject
    response = message.send()
    
    return response


def send_password_reset_email(email, reset_link):
    
    SENDER_MAIL = os.environ.get('SENDER_MAIL')
    MAILTRAP_API_KEY = os.environ.get('MAILTRAP_API_KEY')
    
    mail = mt.Mail(
        sender=mt.Address(email=SENDER_MAIL, name="Robitic Booking Agent"),
        to=[mt.Address(email=email, name="")],
        subject="Reset your password",
        html=f"""
            <!doctype html>
            <html>
            <head>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
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
