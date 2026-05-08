# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

import os
import hashlib
import binascii
import random
import string

import jwt
from datetime import datetime
from flask import current_app, request

# Inspiration -> https://www.vitoshacademy.com/hashing-passwords-in-python/


def hash_pass(password):
    """Hash a password for storing."""
    salt = hashlib.sha256(os.urandom(60)).hexdigest()
    pwdhash = hashlib.pbkdf2_hmac('sha512', password.encode('utf-8'),
                                  salt.encode('ascii'), 100000)
    pwdhash = binascii.hexlify(pwdhash).decode('utf-8')
    return (salt + pwdhash) 


def verify_pass(provided_password, stored_password):
    """Verify a stored password against one provided by user"""
    # stored_password = stored_password.decode('ascii')
    salt = stored_password[:64]
    stored_password = stored_password[64:]
    pwdhash = hashlib.pbkdf2_hmac('sha512',
                                  provided_password.encode('utf-8'),
                                  salt.encode('ascii'),
                                  100000)
    pwdhash = binascii.hexlify(pwdhash).decode('utf-8')
    return pwdhash == stored_password


# Used in API Generator
def generate_token(aUserId):
    now = int(datetime.utcnow().timestamp())
    api_token = jwt.encode(
        {"user_id": aUserId,
         "init_date": now},
        current_app.config["SECRET_KEY"],
        algorithm="HS256"
    )

    return api_token

def generate_random_string():
    length = 36
    # Define the characters you want to include in the random string
    characters = string.ascii_letters + string.digits  # You can customize this as needed

    # Generate the random string of the specified length
    random_string = ''.join(random.choice(characters) for _ in range(length))

    return random_string


def generate_unsubscribe_token():
    length = 128
    # Define the characters you want to include in the random string
    characters = string.ascii_letters + string.digits + "_" + "-" # You can customize this as needed

    # Generate the random string of the specified length
    random_string = ''.join(random.choice(characters) for _ in range(length))

    return random_string

def generate_job_id(length):
    # Define the characters you want to include in the random string
    characters = string.ascii_letters + string.digits # You can customize this as needed

    # Generate the random string of the specified length
    random_string = ''.join(random.choice(characters) for _ in range(length))

    return random_string

if __name__ == "__main__":
    hashed_password = hash_pass("skipmic92")
    print(hashed_password)
    
