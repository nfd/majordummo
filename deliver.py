#!/usr/bin/env python3
import argparse
import email.parser
import email.utils
import functools
import json
import logging
import logging.config
import os
import sys
import smtplib
import sqlite3
import time

logging.basicConfig(level="INFO")
logger = logging.getLogger()

class Config(dict):
    def __init__(self, pathname):
        self['recipients'] = set()
        self['reject_non_recipients'] = True
        self['set_headers'] = []
        self['header_whitelist'] = {'subject', 'received', 'mime-version', 'date', 'from', 'to', 'x-sender',
                                    'user-agent', 'content-type', 'content-transfer-encoding',
                                    'x-gm-message-state', 'x-google-smtp-source', 'x-received'}
        self['db'] = None
        self['per_user_ratelimit_secs'] = 60
        self['archive_dir'] = None
        self['smtp'] = {'host': 'localhost', 'port': 25}
        self['logging'] = {}

        self._load(pathname)

    def _load(self, pathname):
        with open(pathname) as handle:
            config = json.load(handle)

        for key, value in config.items():
            if not key.startswith('_') and key in self:
                typ = str if self[key] is None else type(self[key])
                self[key] = typ(value)

config = None

class Archive:
    def __init__(self):
        self._pathname_base = None
        if 'archive_dir' in config:
            self._dir = config['archive_dir']
            if not os.path.exists(self._dir):
                os.makedirs(self._dir)
        else:
            self._dir = None

    def archive_original(self, message):
        if not self._dir:
            return

        self._create_and_write('.txt', functools.partial(self._write, bytes(message)))
        logger.info("Archived message with base %s", self._pathname_base)

    def _write(self, payload, path):
        with open(path, 'wb') as handle:
            handle.write(payload)

    def log_failed(self, failed_recipients):
        if not self._dir:
            return

        payload = '\n'.join(failed_recipients).encode('utf-8')

        self._create_and_write('-fail.txt', functools.partial(self._write, payload))

    def log_succeeded(self, succeeded_recipients):
        if not self._dir:
            return

        payload = '\n'.join(succeeded_recipients).encode('utf-8')

        self._create_and_write('-succeeded.txt', functools.partial(self._write, payload))

    def _create_and_write(self, ext, func):
        if self._pathname_base is None:
            retry = 0
            while retry < 10:
                try:
                    pathname_base = "{:016.0f}-{:03d}".format(time.time(), retry)
                    func(os.path.join(self._dir, pathname_base + ext))
                    self._pathname_base = pathname_base
                    break
                except FileExistsError:
                    retry += 1
            else:
                raise FileExistsError()
        else:
            func(os.path.join(self._dir, self._pathname_base + ext))

class DB:
    def __init__(self):
        self._conn = None

    def __enter__(self):
        self._conn = sqlite3.connect(config['db'])
        self._conn.execute('CREATE TABLE IF NOT EXISTS most_recent_post(recipient TEXT PRIMARY KEY, timestamp REAL)')
        return self

    def __exit__(self, exc_type, exc_value, tb):
        try:
            self._conn.close()
        except Exception:
            logging.exception("While closing database")

        self._conn = None

    def is_rate_limited(self, recipient):
        with self._conn:
            cur = self._conn.cursor()
            cur.execute('SELECT timestamp FROM most_recent_post WHERE recipient=?', (recipient,))
            results = cur.fetchone()
        if results:
            timestamp = results[0]
        else:
            timestamp = 0

        return timestamp + config['per_user_ratelimit_secs'] > time.time()

    def set_did_just_post(self, recipient):
        with self._conn:
            self._conn.execute('REPLACE INTO most_recent_post(recipient, timestamp) VALUES (?, ?)',
                               (recipient, time.time()))

class Outgoing:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return True

    def send(self, message, recipients):
        """
        Send 'message' to 'recipients'

        Returns: (succeded, failed) where each is a subset of 'recipients'.
        """
        fail = []
        success = set()
        with smtplib.SMTP(host=config['smtp']['host'], port=config['smtp']['port']) as smtp:
            try:
                for recipient in recipients:
                    if self._send_one(smtp, message, recipient):
                        success.add(recipient)
                    else:
                        fail.append(recipient)
            except smtplib.SMTPServerDisconnected:
                fail = list(set(recipients) - success)

        return success, fail

    def _send_one(self, smtp, message, recipient):
        logging.info("Sending email to %s", recipient)
        try:
            smtp.sendmail(config['smtp']['mail_from'], [recipient], bytes(message))
        except Exception as e:
            logging.exception("While sending email")
            if isinstance(e, smtplib.SMTPServerDisconnected):
                raise
            return False

        return True

def _deliver_message(archive, db, message):
    " Deliver email.message.Message object. "
    sender_name, sender_email = email.utils.parseaddr(message['From'])

    if config['reject_non_recipients'] and sender_email not in config['recipients']:
        logging.warn("Not sending message from %s because they're not a list member.", sender_email)
        return

    if db.is_rate_limited(sender_email):
        logging.warning("Not sending message from %s because they are rate limited.", sender_email)
        return

    for header in message:
        if header.lower() not in config['header_whitelist']:
            del message[header]

    for header, value in config['set_headers']:
        del message[header]
        message[header] = value.strip()

    logging.debug("Sending rewritten message %s", message)
    failed = []
    succeeded = []
    with Outgoing() as outgoing:
        succeeded, failed = outgoing.send(message, config['recipients'])

    db.set_did_just_post(sender_email)

    if failed:
        logging.warning("Messages failed for %s", failed)
        archive.log_failed(failed)

    if succeeded:
        archive.log_succeeded(succeeded)

def deliver():
    " Deliver message arriving on stdin. "
    message_bytes = sys.stdin.buffer.read()
    archive = Archive()
    archive.archive_original(message_bytes)

    message = email.parser.BytesParser().parsebytes(message_bytes)
    logging.debug("Original message: %s", message)
    with DB() as db:
        return _deliver_message(archive, db, message)

def main():
    global config

    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    args = parser.parse_args()

    config = Config(args.config)

    if config['logging']:
        logging.config.dictConfig(config['logging'])

    deliver()

if __name__ == '__main__':
    main()

# vim: filetype=python
