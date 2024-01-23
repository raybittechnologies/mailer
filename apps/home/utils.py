
blacklist = ['@email.com', '@example.com','@domain.com','@godaddy.com','@address.com','@filler.com','@xyz.com','@newsletter.com','@mystore.com', 'example@gmail.com', '@sentry', 'mail@mail.com']

def check_blacklisted(email):
    return all([black not in email for black in blacklist])