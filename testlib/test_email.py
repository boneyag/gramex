import os
import random
from unittest import TestCase
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from gramex.services.emailer import message, SMTPMailer


class TestEmailer(TestCase):
    def eq(self, msg1, msg2):
        '''Compare 2 messages ensuring random boundary values are the same'''
        random.seed(0)
        msg1 = msg1.as_string()
        random.seed(0)
        msg2 = msg2.as_string()
        self.assertEqual(msg1, msg2)

    def test_message(self):
        text = 'This is some text'
        html = '<h1>Heading</h1>\n<p>This is a paragraph</p>'
        msg = message(body=text)
        self.eq(message(body=text), MIMEText(text, 'plain'))
        self.eq(message(html=html), MIMEText(html, 'html'))

        msg = MIMEMultipart('alternative')
        msg.attach(MIMEText(text, 'plain'))
        msg.attach(MIMEText(html, 'html'))
        self.eq(message(body=text, html=html), msg)

    def test_attachment(self):
        folder = os.path.dirname(os.path.abspath(__file__))
        img = os.path.join(folder, 'small-image.jpg')
        self.check_attachment(img)

        with open(img, 'rb') as handle:
            contents = handle.read()
        self.check_attachment({'content_type': 'image/jpeg', 'body': contents})
        self.check_attachment({'filename': img, 'body': contents})

    def check_attachment(self, img):
        msg = message(body='text', attachments=[img])
        img_part = list(msg.walk())[-1]
        self.assertEqual(img_part.get_content_type(), 'image/jpeg')
