import io, csv, email, json

from email import header
from email.utils import getaddresses
from email.utils import getaddresses

from bs4 import BeautifulSoup

import arxiv
import chardet
import requests

def arxiv_to_csv(q):
    results = arxiv.query(q, prune=True, start=0, max_results=100)

    output = io.StringIO()
    writer = csv.writer(output)

    N = len(results)

    print('arxiv search for', q, '; results:', N)
    for result in results:
        for author in result['authors']:
            for author2 in result['authors']:
                if author != author2:
                    writer.writerow([author, author2, result['title']])

    return output.getvalue()


def hal_to_csv(q):
    params = {
        'fl': 'authFullName_s,title_s',
        'q': q,
        'rows': 200,
    }
    resp = requests.get('https://api.archives-ouvertes.fr/search/', params=params)
    results = resp.json()['response']['docs']

    output = io.StringIO()
    writer = csv.writer(output)

    N = len(results)

    print('HAL search for', q, '; results:', N)
    for result in results:
        for author in result['authFullName_s']:
            for author2 in result['authFullName_s']:
                if author != author2:
                    writer.writerow([author, author2, result['title_s'][0]])

    return output.getvalue()


def mbox_to_csv(mbox, subject_only):
    output = io.StringIO()
    writer = csv.writer(output)

    mail = None

    def add_mail():
        if mail:
            msg = email.message_from_string(mail)

            subject = header.make_header(header.decode_header(msg['Subject']))
            body = str(subject)
            if not subject_only:
                body += '\n'

                def parse_payload(message):
                    if message.is_multipart():
                        for part in message.get_payload(): 
                            yield from parse_payload(part)
                    else:
                        cte = message.get_content_type()
                        if 'plain' in cte or 'html' in cte:
                            yield message, message.get_payload(decode=True)

                for submsg, part in parse_payload(msg):
                    content_type = submsg.get_content_type()
                    content = ''
                    def decode():
                        charset = submsg.get_content_charset('utf-8')
                        try:
                            return part.decode(charset)
                        except UnicodeDecodeError:
                            charset = chardet.detect(part)['encoding']
                            return part.decode(charset)
                    if 'plain' in content_type:
                        content = decode()
                    if 'html' in content_type:
                        content = BeautifulSoup(decode()).text
                    body += '\n' + content

            if msg['To'] and msg['From']:
                for _, sender in getaddresses(msg.get_all('from', [])):
                    tos = msg.get_all('to', [])
                    ccs = msg.get_all('cc', [])
                    resent_tos = msg.get_all('resent-to', [])
                    resent_ccs = msg.get_all('resent-cc', [])
                    all_recipients = getaddresses(tos + ccs + resent_tos + resent_ccs)
                    for _, dest in all_recipients:
                        writer.writerow([sender, dest, body])

    for line in mbox:
        if line.startswith('From '):
            add_mail()
            mail = ''
        if mail is not None: # ignore email without headers
            mail += line
    add_mail()  
    return output.getvalue()
