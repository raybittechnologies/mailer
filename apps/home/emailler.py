# import smtplib
# from email.mime.text import MIMEText
# from email.mime.multipart import MIMEMultipart


# def send_email(recipient_email, subject, message):
#     sender_email = 'nvest.dev2021@gmail.com'
#     sender_password = 'nvest.pass2021'
#     # Create an SMTP connection
#     try:
#         # Create a MIMEText object
#         msg = MIMEMultipart()
#         msg['From'] = sender_email
#         msg['To'] = recipient_email
#         msg['Subject'] = subject

#         # Attach the message to the email
#         msg.attach(MIMEText(message, 'plain'))

#         server = smtplib.SMTP('smtp.gmail.com', 587)
#         server.starttls()  # Use TLS for security
#         server.login(sender_email, sender_password)

#         # Send the email
#         server.sendmail(sender_email, recipient_email, msg.as_string())

#         # Close the SMTP server
#         server.quit()
#         data = {
#             "status": "successful",
#             "msg": "Email sent successfully"
#         }
#         return data
#     except Exception as e:
#         data = {
#             "status": "failed",
#             "msg": str(e)
#         }
#         return data


# recipient_email = 'lightthree718@gmail.com'
# subject = 'Hello, this is a test email'
# message = 'This is the body of the email.'

# send_email(recipient_email, subject, message)
# # import smtplib

# # sender = "Private Person <from@example.com>"
# # receiver = "A Test User <to@example.com>"

# # message = f"""\
# # Subject: Hi Mailtrap
# # To: {receiver}
# # From: {sender}

# # This is a test e-mail message."""

# # with smtplib.SMTP("sandbox.smtp.mailtrap.io", 2525) as server:
# #     server.login("f6102b697ab864", "88f559b5dbdee4")
# #     server.sendmail(sender, receiver, message)

import mailtrap as mt

mail = mt.MailFromTemplate(
    sender=mt.Address(email="info@soundheartmusic.com", name="Mailtrap Test"),
    to=[mt.Address(email="nvest.dev2021@gmail.com")],
    template_uuid="eba046d2-f2d5-490c-9b87-7c5ecf558925",
    template_variables={
      "view_data_link": "Test_View_data_link",
      "user_email": "Test_User_email",
      "pass_reset_link": "Test_Pass_reset_link"
    }
)

client = mt.MailtrapClient(token="6752e77e8028a73e597116dfe06e4960")
res = client.send(mail)
print(res)