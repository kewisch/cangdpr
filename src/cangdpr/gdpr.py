import http.client
import logging
import os.path
import stat

import click
import yaml
from pydiscourse.exceptions import DiscourseClientError, DiscourseError

from .discourse import CanDiscourseClient
from .indico import Indico
from .salesforce import CanSalesforce

SF_GDPR_OWNER = "00G4K000000gkG9UAI"  # Assignee: GDPR - Snap
SF_COMPANY = "canonical"

DISCOURSE_USER_SQL = (
    """
-- [params]
-- string :email

SELECT u.id, u.username, ue.email
  FROM user_emails ue
  JOIN users u ON u.id = ue.user_id
 WHERE email = :email
"""
).strip()

yaml.add_representer(
    type(None), lambda self, _: self.represent_scalar("tag:yaml.org,2002:null", "")
)


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

    try:
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

    except pydiscourse.exceptions.DiscourseServerError as e:
        print("Discourse Error: ", str(e), e.request.url)


@main.command()
@click.argument("username")
@click.pass_obj
def newuser(ctxo, username):
    config = {
        "services": {
            "discourse": {},
            "indico": {
                "prod": {
                    "url": "https://events.canonical.com",
                    "key": "Set this up on https://events.canonical.com/user/tokens/",
                }
            },
        },
        "tools": {
            "cangdpr": {"discourses": ctxo.toolconfig["discourses"]},
            "profile": "/path/to/a/new/firefox/profile",
        },
    }

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

        try:
            group = discourse.group("gdpr_lookups")
        except DiscourseClientError as e:
            if "resource could not be found" not in str(e):
                raise e
            print("\tDiscourse does not have lookups group")
            group = None

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


@main.command()
@click.argument("alias")
@click.argument("url", required=False)
@click.argument("username", required=False)
@click.pass_obj
def newdiscourse(ctxo, alias, url, username):
    if alias in ctxo.serviceconfig["discourse"]:
        key = ctxo.serviceconfig["discourse"][alias]["key"]
        url = url or ctxo.serviceconfig["discourse"][alias]["url"]
        username = username or ctxo.serviceconfig["discourse"][alias]["username"]
    else:
        if not url or not username:
            raise click.BadUsage("url and username are mandatory for new discourses")

        if not url.startswith("http"):
            url = "https://" + url

        print("Please enter your API key from an admin account: ", end="", flush=True)
        key = input()

    config = {
        "services": {
            "discourse": {alias: {"url": url, "username": username, "key": key}}
        },
        "tools": {"cangdpr": {"discourses": {alias: None}}},
    }

    discourse = CanDiscourseClient(alias, config["services"]["discourse"][alias], {})

    try:
        queries = discourse.data_explorer_queries()
        supports_dataexplorer = True
    except DiscourseClientError:
        supports_dataexplorer = False

    if supports_dataexplorer:
        print("Discourse supports data explorer")
        try:
            print("Creating gdpr_lookups group...", end="", flush=True)
            group = discourse.add_group(
                "gdpr_lookups",
                "Permissions for GDPR Lookups",
                owner_usernames=username,
                visibility_level=4,
                members_visibility_level=4,
                mentionable_level=0,
                messageable_level=0,
            )
            print("done")
        except DiscourseError as e:
            if "Name has already been taken" not in str(e):
                raise e
            print("group already exists")
            group = discourse.group("gdpr_lookups")

        gdprquery = next(
            (query for query in queries if query["name"] == "gdpr_email_lookup"), None
        )

        if not gdprquery:
            print("GDPR lookup query missing, creating now...", end="", flush=True)
            gdprquery = discourse.data_explorer_create_query("gdpr_email_lookup")
            print("done")

        print("Setting query SQL and permissions...", end="", flush=True)
        if (
            gdprquery["sql"] != DISCOURSE_USER_SQL
            or group["id"] not in gdprquery["group_ids"]
        ):
            discourse.data_explorer_edit_query(
                gdprquery["id"], sql=DISCOURSE_USER_SQL, group_ids=group["id"]
            )
            print("done")
        else:
            print("already correct")

        config["tools"]["cangdpr"]["discourses"][alias] = {
            "dataquery_gdpr_id": gdprquery["id"]
        }
    else:
        print(
            "Discourse does not support data explorer. Lookup only covers primary email."
        )
        print("All that is needed is people having moderator permissions")

    print("Here is your config")
    print(yaml.dump(config))


if __name__ == "__main__":
    main(prog="cangdpr")
