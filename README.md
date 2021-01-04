Majordummo
==========
... is a group email tool for small, private mailing lists. View it as one step above a long CC: list.

It's designed to integrate with an existing mail delivery agent (e.g. a Postfix installation) and was made because
Postfix can almost, but not quite, do exactly what I want already.

Prerequisites
-------------
 * Python 3.6 or above

Majordummo is implemented as a single file written in Python with no external dependencies.

Features
--------
 * Accepts mail
 * Resends it to a list of people
 * Drops emails if they're sent by non-members (optional)
 * Adds Reply-To header (optional)
 * Writes messages and delivery status to the filesystem
 * Logs everything
 * That's it

Majordummo has no cronjobs or daemons, and only runs when the MDA invokes it to process mail sent to the list. It will
only ever send email to the list of recipients which is set in its configuration file -- it doesn't, for example, send
bounce messages. It's configured using a JSON file and has no GUI.

Installation
------------
After creating a configuration file, create an account, or virtual alias, for the mailing list name, and set deliver.py
to run when mail is delivered to that account.

There are plenty of ways to do this. For example, you could "|/path/to/deliver.py --config /path/to/config" in
/etc/aliases, or you could run it as part of a set of Procmail rules, or you could configure the Postfix pipe delivery
agent to backend on to it, or...

Configuration
-------------
Configuration is supplied by a JSON file. Majordummo has a very minimal configuration, but you will probably want to
change all of it. Copy `config-example.json` to `config.json` and customise it. Fields to change:

 * `recipients`: The people on your list.
 * `reject_non_recipients`: messages from non-list members will be dropped. The sender will not be notified, but the
   action is logged. Recommended.
 * `set_headers`: A list of headers to replace (if they exist) or add (if they don't) to outgoing messages.
 * `archive_dir`: A directory name to write emails and delivery status. Can be set to `null` if you don't want archives.
 * `smtp`: Mail server details. You will want to change `mail_from`.
 * `logging`: A Python logging configuration -- note that `logging/handlers/file/filename` is a filename to write logs
   to.

Make sure you've set `archive_dir` and `logging/handlers/file/filename` to valid paths which are accessible by the user
running `deliver.py` (see "Running as a different user").

Running as a different user
----------------------------
Because it writes logs and archives emails, It's convenient to have majordummo run as its own user. I do this using a
suid wrapper binary, but you can also do it by setting up a `sudo` rule and including `sudo` in your alias, or by using
something like `procmail`.

Testing
-------
When testing, it's best to set the list of `recipients` in your config to just yourself.

Testing can be split into two parts: 1) does my configuration do what I want? and 2) does my MDA correctly invoke
majordummo?

You can test the configuration by running deliver.py directly with an email:

    cat email.txt | python3 deliver.py --config /path/to/config.json

If that works, then send a test email to the list. Your MDA will log message delivery, so check those logs first. After
that, check the log file you've configured in your `config.json`.

