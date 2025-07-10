# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""
import datetime

from flask_login import UserMixin
from apps import db
from sqlalchemy import create_engine, Column, Integer, String, orm
from flask_bcrypt import generate_password_hash, check_password_hash
from apps.authentication.util import generate_random_string, generate_unsubscribe_token
from sqlalchemy.dialects.mysql import LONGTEXT, JSON
import uuid
'''
Add your models below
'''


# Book Sample
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(64))


class Yelpurl(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(254))
    product_url = db.Column(db.Text)
    userid = db.Column(db.Integer)
    state = db.Column(db.String(20))
    create_datetime = db.Column(db.DateTime(), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, index=True)
    latitude = db.Column(db.String(255))
    longitude = db.Column(db.String(255))


class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    venue_type = db.Column(db.String(255))
    website = db.Column(db.String(1024))
    phone = db.Column(db.String(120))
    address = db.Column(db.String(1024))
    facebook = db.Column(db.Text)
    instagram = db.Column(db.String(255))
    twitter = db.Column(db.String(255))
    email1 = db.Column(db.String(255), index=True)
    email2 = db.Column(db.String(255), index=True)
    email3 = db.Column(db.String(255), index=True)
    email4 = db.Column(db.String(255), index=True)
    fbemail1 = db.Column(db.String(255), index=True)
    fbemail2 = db.Column(db.String(255), index=True)
    bademail = db.Column(db.String(255), index=True)
    url_id = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.String(255), nullable=False)
    biz_id = db.Column(db.String(255), nullable=False)
    is_credited = db.Column(db.Integer, default=0) # 1: credited, 0: not credited 2 : ignored
    first_name1 = db.Column(db.String(255))
    first_name2 = db.Column(db.String(255))
    first_name3 = db.Column(db.String(255))
    first_name4 = db.Column(db.String(255))
    first_name5 = db.Column(db.String(255))
    first_name6 = db.Column(db.String(255))
    city = db.Column(db.String(255))
    state = db.Column(db.String(255))
    zip = db.Column(db.String(255))
    country = db.Column(db.String(255))
    latitude = db.Column(db.String(255))
    longitude = db.Column(db.String(255))
    thumnailurl = db.Column(db.String(1024))
    
    __table_args__ = (
        db.Index('sevice-idx', "url_id", "user_id", "biz_id", unique=True), 
        db.Index('biz-idx', "biz_id"),
    )
    
    def to_dict(self):
        return {column.name: getattr(self, column.name) if getattr(self, column.name) else '' for column in self.__table__.columns}


class Uploadedservice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128))
    venue_type = db.Column(db.String(255))
    email =  db.Column(db.String(255), index=True)
    is_bad =  db.Column(db.Integer, default=0)
    user_id = db.Column(db.String(32))
    file_id = db.Column(db.String(255))
    create_datetime = db.Column(db.DateTime(), default=datetime.datetime.utcnow)
    unsubscribe_token = db.Column(db.String(128), nullable=False, default=generate_unsubscribe_token, index=True)
    is_unsubscribed = db.Column(db.Integer, default=0)
    website = db.Column(db.String(1024))
    phone = db.Column(db.String(32), index=True)
    address = db.Column(db.String(191), index=True)
    facebook = db.Column(db.Text)
    firstname = db.Column(db.String(255))
    customtext = db.Column(db.String(1024))
    originalemail = db.Column(db.Text)
    bademail = db.Column(db.String(255), index=True)
    biz_id = db.Column(db.String(255), index=True)
    is_archived = db.Column(db.Integer, default=0)  # 0: not archived, 1: archived
    
    __table_args__ = (
        db.Index('uploaded-idx', "email", "user_id"),
        db.Index('bademail-idx', "bademail", "user_id"),
        # index for user_id, biz_id, file_id
        db.Index('uploaded-service-idx', "user_id", "biz_id"),
        # unique constraint for name, email, user_id, type, phone, address
        db.UniqueConstraint('name', 'email', 'user_id', 'phone', 'address', name='uploaded_service_name_email_user_id_uc'),
    )
    
class Uploadedcontactfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255))
    filepath = db.Column(db.String(1024))
    description = db.Column(db.String(1024))
    user_id = db.Column(db.String(255), nullable=False, index=True)
    create_datetime = db.Column(db.DateTime(), default=datetime.datetime.utcnow, index=True)
    is_archived = db.Column(db.Integer, default=0)  # 0: not archived, 1: archived
    
    
class Admin(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(String(120))
    email = db.Column(String(120))
    password_hash = db.Column(String(128))
    role = db.Column(String(10))

    def __init__(self, name, email, password, role):
        self.name = name
        self.email = email
        self.password_hash = generate_password_hash(password).decode('utf-8')
        self.role = role

    def save(self):
        db.session.add(self)
        db.session.commit()

    @staticmethod
    def find_by_user(user):
        return Admin.query.filter_by(email=user.email, id=user.id).first()

    @staticmethod
    def find_by_email(email):
        return Admin.query.filter_by(email=email).first()

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Template(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_name = db.Column(db.String(255))
    template_desc = db.Column(db.String(1024))
    status = db.Column(db.String(16))
    userid = db.Column(db.Integer)
    tempid = db.Column(db.String(36), nullable=False, default=generate_random_string, index=True)
    create_datetime = db.Column(db.DateTime(), default=datetime.datetime.utcnow, index=True)
    

class Action(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action_name = db.Column(db.String(255))
    subject = db.Column(db.String(255))
    fromname = db.Column(db.String(255))
    message = db.Column(db.Text)
    waitdays = db.Column(db.Integer)
    tempid = db.Column(db.Integer)
    userid = db.Column(db.Integer)
    create_datetime = db.Column(db.DateTime(), default=datetime.datetime.utcnow, index=True)


class Automation(db.Model):
    id = db.Column(db.Integer, primary_key =True)
    action_id = db.Column(db.Integer, index=True)
    action_name = db.Column(db.String(255))
    group_number = db.Column(db.Integer)
    group_count = db.Column(db.Integer)
    action_datetime = db.Column(db.DateTime())
    job_id = db.Column(db.String(191), index=True)
    userid = db.Column(db.Integer, index=True)
    status = db.Column(db.String(16)) # pending, running, completed, failed
    campaignid = db.Column(db.String(32), index=True) # Created another unique id for campaign, because it should be used in query string.
    is_archived = db.Column(db.Integer, default=0)  # 0: not archived, 1: archived


class Campaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaignid = db.Column(db.String(32))
    contact_name = db.Column(db.String(255))
    templatename = db.Column(db.String(255))
    userid = db.Column(db.Integer)
    create_datetime = db.Column(db.DateTime(), default=datetime.datetime.utcnow)
    is_archived = db.Column(db.Integer, default=0)  # 0: not archived, 1: archived
    
        
class Email(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(191), index=True)
    email = db.Column(db.String(255))
    venue = db.Column(db.String(255))
    is_sent = db.Column(db.Integer, default=0)
    is_opened = db.Column(db.Integer, default=0)
    is_bounced = db.Column(db.Integer, default=0)
    is_unsubscribed = db.Column(db.Integer, default=0)
    updated_datetime = db.Column(db.DateTime(), onupdate=datetime.datetime.utcnow, default=datetime.datetime.utcnow)
    unsubscribe_token = db.Column(db.String(128), nullable=False, index=True) # it is synced with unsubscribe_token in Uploadedservice table
    is_replied = db.Column(db.Integer, default=0)
    mail_id = db.Column(db.String(255), index=True)
    firstname = db.Column(db.String(255))
    customtext = db.Column(db.String(1024))
    originalemail = db.Column(db.String(255))
    is_archived = db.Column(db.Integer, default=0)  # 0: not archived, 1: archived
    
    
class UserCredit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    userid = db.Column(db.Integer)
    credit = db.Column(db.Integer)
    monthly_credit = db.Column(db.Integer, default=10)
    create_datetime = db.Column(db.DateTime(), default=datetime.datetime.utcnow)
    update_datetime = db.Column(db.DateTime(), onupdate=datetime.datetime.utcnow, default=datetime.datetime.utcnow)


class FirstName(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), index=True, unique=True)
    first_name = db.Column(db.String(255))


class UserCampaignSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    userid = db.Column(db.Integer)
    emails_daily_limit = db.Column(db.Integer, default=150)
    create_datetime = db.Column(db.DateTime(), default=datetime.datetime.utcnow)
    update_datetime = db.Column(db.DateTime(), onupdate=datetime.datetime.utcnow, default=datetime.datetime.utcnow)

class HowToFAQ(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # field to save html with image imbeded
    content = db.Column(LONGTEXT)
    create_datetime = db.Column(db.DateTime(), default=datetime.datetime.utcnow)
    update_datetime = db.Column(db.DateTime(), onupdate=datetime.datetime.utcnow, default=datetime.datetime.utcnow)

class PushNotificationInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    userid = db.Column(db.Integer, index=True)
    # push notification subscription info json
    subscription_info = db.Column(JSON)
    create_datetime = db.Column(db.DateTime(), default=datetime.datetime.utcnow)
    update_datetime = db.Column(db.DateTime(), onupdate=datetime.datetime.utcnow, default=datetime.datetime.utcnow)

class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    userid = db.Column(db.Integer, index=True)  
    job_id = db.Column(db.String(191), index=True)
    title = db.Column(db.String(1024))
    note = db.Column(db.Text)
    name = db.Column(db.String(191), index=True)
    email = db.Column(db.String(255))
    phone = db.Column(db.String(255))
    venue = db.Column(db.String(255))
    note_template = db.Column(db.Text)
    reminder_time = db.Column(db.DateTime(), index=True)
    status = db.Column(db.String(16), default='active') # active, completed, past
    create_datetime = db.Column(db.DateTime(), default=datetime.datetime.utcnow)
    update_datetime = db.Column(db.DateTime(), onupdate=datetime.datetime.utcnow, default=datetime.datetime.utcnow)

    #  create index for userid , email
    __table_args__ = (
        db.Index('reminder-idx', "userid", "email", unique=True),
    )



class GlobalSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), index=True, unique=True)
    value = db.Column(db.String(1024))

