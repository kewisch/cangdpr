import http.client
import logging
import os.path
import stat

import click
import yaml

from .discourse import CanDiscourseClient
from .indico import Indico
from .salesforce import CanSalesforce

SF_GDPR_OWNER = "00G4K000000gkG9UAI"  # Assignee: GDPR - Snap
SF_COMPANY = "canonical"


class Context:
    def __init__(self, config, sid=None, dry=False, debug=False):
        self.toolconfig = config["tools"]["cangdpr"]
        self.serviceconfig = config["services"]
        self.debug = debug

        self.discourses = []
        for discourse, data in self.toolconfig.get("discourses", {}).items():
            if discourse not in self.serviceconfig.get("discourse", {}):
                raise Exception("Missing discourse: " + discourse)

            self.discourses.append(
                CanDiscourseClient(self.serviceconfig["discourse"][discourse], data)
            )

        if not len(self.discourses):
            raise click.UsageError("Missing discourse config")

        try:
            self.indico = Indico(self.serviceconfig["indico"]["prod"])
        except KeyError:
            raise click.UsageError("Missing indico config")

        profile = self.toolconfig.get("profile", None)
        binary = self.toolconfig.get("binary", None)
        self.sf = CanSalesforce(
            SF_COMPANY,
            SF_GDPR_OWNER,
            sid=sid,
            dry=dry,
            profile=profile,
            binary=binary,
        )

        if debug:
            logging.basicConfig()
            logging.getLogger().setLevel(logging.DEBUG)
            requests_log = logging.getLogger("requests.packages.urllib3")
            requests_log.setLevel(logging.DEBUG)
            requests_log.propagate = True
            http.client.HTTPConnection.debuglevel = 1

    def profile_urls_get(self, email):
        urls = []
        for discourse in self.discourses:
            user = discourse.dataquery_gdpr_user(email)
            if user:
                urls.append(discourse.format_user(user))

        data = self.indico.user_by_email(email)
        if data:
            urls.append(self.indico.format_user(data[0]))

        return urls


@click.command()
@click.option("--debug", is_flag=True, default=False, help="Enable debugging.")
@click.option("--config", default="~/.canonicalrc", help="Config file location.")
@click.option(
    "-l",
    "--query-tasks",
    is_flag=True,
    help="EMAILS are task ids, not email addresses.",
)
@click.option("--dry", is_flag=True, default=False, help="Dry run on Salesforce.")
@click.option("--sid", help="Salesforce token.")
@click.option(
    "--since", type=int, help="Look back N months instead of taking open items."
)
@click.argument("emails", required=False, nargs=-1)
def main(debug, config, query_tasks, dry, sid, since, emails):
    """
    GDPR lookup for the community team at Canonical

    If no email is specified, Salesforce will be queried for pending tasks
    """
    configpath = os.path.expanduser(config)

    # Check if the config file is locked to mode 600. Add a loophole in case it is being passed in
    # via pipe, it appears on macOS the pipes are mode 660 instead.
    statinfo = os.stat(configpath, dir_fd=None, follow_symlinks=True)
    if (statinfo.st_mode & (stat.S_IROTH | stat.S_IRGRP)) != 0 and not stat.S_ISFIFO(
        statinfo.st_mode
    ):
        raise click.ClickException(f"Credentials file {config} is not chmod 600")

    with open(configpath) as fd:
        config = yaml.safe_load(fd)

    if not config:
        raise click.ClickException(f"Could not load config file {configpath}")

    ctxo = Context(config, debug=debug, sid=sid, dry=dry)

    if len(emails):
        lookup_gdpr(ctxo, emails, query_tasks)
    else:
        lookup_salesforce_gdpr(ctxo, since)


def lookup_gdpr(ctxo, emails, query_tasks=False):
    for email in emails:
        if query_tasks:
            email = ctxo.sf.get_task_email(email)

        urls = ctxo.profile_urls_get(email)
        if len(urls) < 1:
            print("{} has no account data".format(email))
        else:
            print("{}:\n\t{}".format(email, "\n\t".join(urls)))


def lookup_salesforce_gdpr(ctxo, since=None):
    tasks = ctxo.sf.get_tasks(since)

    for record in tasks:
        urls = ctxo.profile_urls_get(record.email)
        if len(urls) < 1:
            print(
                "{} ({}) has no account data, marking complete".format(
                    record.email, record.id
                )
            )
            ctxo.sf.mark_complete(record.id)
        else:
            print(
                "{}: {}\n\t{}".format(
                    record.email, ctxo.sf.task_url(record.id), "\n\t".join(urls)
                )
            )


if __name__ == "__main__":
    main(prog="cangdpr")
