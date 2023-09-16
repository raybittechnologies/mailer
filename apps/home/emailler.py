import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(recipient_email, subject, message):
    sender_email = 'usmantahirhome@gmail.com'
    sender_password = 'jukxavumjgqoshfs'
    # Create an SMTP connection
    try:
        # Create a MIMEText object
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject

        # Attach the message to the email
        msg.attach(MIMEText(message, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # Use TLS for security
        server.login(sender_email, sender_password)

        # Send the email
        server.sendmail(sender_email, recipient_email, msg.as_string())

        # Close the SMTP server
        server.quit()
        data = {
            "status": "successful",
            "msg": "Email sent successfully"
        }
        return data
    except Exception as e:
        data = {
            "status": "failed",
            "msg": str(e)
        }
        return data


# recipient_email = 'usmankiani88.uk@gmail.com'
# subject = 'Hello, this is a test email'
# message = 'This is the body of the email.'
#
# send_email("wajiamansab786@gmail.com", subject, message)