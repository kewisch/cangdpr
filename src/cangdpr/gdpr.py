import argparse
import http.client
import logging
import os.path
import stat
import sys

import yaml

from .discourse import CanDiscourseClient
from .indico import Indico
from .salesforce import CanSalesforce

SF_GDPR_OWNER = "00G4K000000gkG9UAI"  # Assignee: GDPR - Snap
SF_COMPANY = "canonical"


def main():
    def profile_urls_get(email):
        urls = []
        data = ubuntudiscourse.user_by_email(email)
        if len(data):
            urls.append(ubuntudiscourse.format_user(data[0]))

        data = snapdiscourse.user_by_email(email)
        if len(data):
            urls.append(snapdiscourse.format_user(data[0]))

        data = indico.user_by_email(email)
        if data:
            urls.append(indico.format_user(data[0]))

        return urls

    parser = argparse.ArgumentParser(
        prog="cangdpr",
        description="GDPR lookup for the community team at Canonical",
        epilog="If no email is specified, Salesforce will be queried for pending tasks",
    )
    parser.add_argument(
        "email", nargs="*", help="one or more email addresses to look up"
    )
    parser.add_argument(
        "-l",
        "--query-tasks",
        action="store_true",
        help="Emails are task ids, not emails",
    )
    parser.add_argument(
        "-n", "--dry", action="store_true", help="dry run on Salesforce"
    )
    parser.add_argument("-s", "--sid", help="Salesforce SID Cookie (optional)")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debugging")
    parser.add_argument(
        "--config", default="~/.canonicalrc", help="Config file locataion"
    )
    args = parser.parse_args()

    configpath = os.path.expanduser(args.config)
    # Check if the config file is locked to mode 600. Add a loophole in case it is being passed in
    # via pipe, it appears on macOS the pipes are mode 660 instead.
    statinfo = os.stat(configpath, dir_fd=None, follow_symlinks=True)
    if (statinfo.st_mode & (stat.S_IROTH | stat.S_IRGRP)) != 0 and not stat.S_ISFIFO(
        statinfo.st_mode
    ):
        print(f"Credentials file {configpath} is not chmod 600")
        sys.exit(1)

    with open(configpath) as fd:
        config = yaml.safe_load(fd)

    ubuntudiscourse = CanDiscourseClient(config["services"]["discourse"]["ubuntu"])
    snapdiscourse = CanDiscourseClient(config["services"]["discourse"]["snap"])
    indico = Indico(config["services"]["indico"]["prod"])
    profile = config["tools"].get("cangdpr", {}).get("profile", None)
    binary = config["tools"].get("cangdpr", {}).get("binary", None)
    sf = CanSalesforce(
        SF_COMPANY,
        SF_GDPR_OWNER,
        sid=args.sid,
        dry=args.dry,
        profile=profile,
        binary=binary,
    )

    if args.debug:
        level = logging.DEBUG
        logging.basicConfig()
        logging.getLogger().setLevel(level)
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(level)
        requests_log.propagate = True

        if level == logging.DEBUG:
            http.client.HTTPConnection.debuglevel = 1

    if len(args.email):
        for email in args.email:
            if args.query_tasks:
                email = sf.get_task_email(email)

            urls = profile_urls_get(email)
            if len(urls) < 1:
                print("{} has no account data".format(email))
            else:
                print("{}:\n\t{}".format(email, "\n\t".join(urls)))
    else:
        data = sf.get_tasks()
        for record in data:
            urls = profile_urls_get(record.email)
            if len(urls) < 1:
                print(
                    "{} ({}) has no account data, marking complete".format(
                        record.email, record.id
                    )
                )
                sf.mark_complete(record.id)
            else:
                print(
                    "{}: {}\n\t{}".format(
                        record.email, sf.task_url(record.id), "\n\t".join(urls)
                    )
                )


if __name__ == "__main__":
    main()
