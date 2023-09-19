# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""
from flask_login import UserMixin

from apps import db
from sqlalchemy import create_engine, Column, Integer, String, orm
from flask_bcrypt import generate_password_hash, check_password_hash

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
    product_url = db.Column(db.String(254))
    userid = db.Column(db.String(254))
    state = db.Column(db.String(20))


class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255))
    name = db.Column(db.String(255))
    venue_type = db.Column(db.String(255))
    website = db.Column(db.String(255))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    facebook = db.Column(db.String(255))
    instagram = db.Column(db.String(255))
    twitter = db.Column(db.String(255))
    email1 = db.Column(db.String(255))
    email2 = db.Column(db.String(255))
    email3 = db.Column(db.String(255))
    email4 = db.Column(db.String(255))
    fbemail1 = db.Column(db.String(255))
    fbemail2 = db.Column(db.String(255))
    bademail = db.Column(db.String(255))
    url_id = db.Column(db.String(255))
    user_id = db.Column(db.String(255))
    biz_id = db.Column(db.String(255))


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