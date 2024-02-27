
blacklist = ['@email.com', '@example.com','@domain.com','@godaddy.com','@address.com','@filler.com','@xyz.com','@newsletter.com','@mystore.com', 'example@gmail.com', '@sentry', 'mail@mail.com', '@mail.com', 'example@mail.com']

def check_blacklisted(email):
    return all([black not in email for black in blacklist] + ['@' in email])


if __name__ == '__main__':
    print(check_blacklisted(""))
