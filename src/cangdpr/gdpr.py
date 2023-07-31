import http.client
import logging
import os.path
import stat

import click
import yaml
from pydiscourse.exceptions import DiscourseClientError

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
                CanDiscourseClient(
                    discourse, self.serviceconfig["discourse"][discourse], data
                )
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


@click.group(invoke_without_command=True)
@click.option("--debug", is_flag=True, default=False, help="Enable debugging.")
@click.option("--config", default="~/.canonicalrc", help="Config file location.")
@click.option("--dry", is_flag=True, default=False, help="Dry run on Salesforce.")
@click.option("--sid", help="Salesforce token.")
@click.pass_context
def main(ctx, debug, config, dry, sid):
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

    ctx.obj = Context(config, debug=debug, sid=sid, dry=dry)

    if ctx.invoked_subcommand is None:
        ctx.invoke(sftasks)


@main.command()
@click.option(
    "-l",
    "--query-tasks",
    is_flag=True,
    help="EMAILS are task ids, not email addresses.",
)
@click.argument("emails", required=False, nargs=-1)
@click.pass_obj
def lookup(ctxo, query_tasks, emails):
    for email in emails:
        if query_tasks:
            email = ctxo.sf.get_task_email(email)

        urls = ctxo.profile_urls_get(email)
        if len(urls) < 1:
            print("{} has no account data".format(email))
        else:
            print("{}:\n\t{}".format(email, "\n\t".join(urls)))


@main.command()
@click.option(
    "--since", type=int, help="Look back N months instead of taking open items."
)
@click.pass_obj
def sftasks(ctxo, since):
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


@main.command()
@click.argument("username")
@click.pass_obj
def newuser(ctxo, username):
    config = {
        "services": {"discourse": {}},
        "tools": {
            "cangdpr": {"discourses": ctxo.toolconfig["discourses"]},
            "profile": "/path/to/a/new/firefox/profile",
        },
    }

    def represent_none(self, _):
        return self.represent_scalar("tag:yaml.org,2002:null", "")

    yaml.add_representer(type(None), represent_none)

    for discourse in ctxo.discourses:
        print(f"Processing {discourse.name}")
        print("\tCreating API key...", end="", flush=True)
        keydesc = "GDPR " + username
        keys = discourse.get_api_keys()
        foundkey = next(
            (
                key
                for key in keys
                if key["revoked_at"] is None and key["description"] == keydesc
            ),
            None,
        )
        if foundkey:
            print(f"already exsists ({foundkey['truncated_key']}...)")
            config["services"]["discourse"][discourse.name] = {
                "url": discourse.host,
                "username": username,
                "key": foundkey["truncated_key"] + "... (please check your records)",
            }
        else:
            key = discourse.create_api_key(username, "GDPR " + username)
            config["services"]["discourse"][discourse.name] = {
                "url": discourse.host,
                "username": username,
                "key": key,
            }
            print("done")

        group = discourse.group("gdpr_lookups")
        if group:
            try:
                print(
                    f"\tAdding {username} to gdpr_lookups group...", end="", flush=True
                )
                discourse.group_add_user(group["id"], username)
                print("done")
            except DiscourseClientError as e:
                if "already a member" not in str(e):
                    raise e
                print("already a member")

    print("\nHere is your config:\n")
    print(yaml.dump(config))


if __name__ == "__main__":
    main(prog="cangdpr")
