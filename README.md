# cangdpr

Tool to automate GDPR lookups on the Community Team at Canonical. Gets the job done.

## Usage

This project uses setuptools via `pyproject.toml`. Install it as you like, one way to do so is using
`pipx install --editable .` in the source repo. It installs a `cangdpr` command:

```
usage: cangdpr [-h] [-n] [-s SID] [-d] [email [email ...]]

GDPR lookup for the community team at Canonical

positional arguments:
  email              one or more email addresses to look up

optional arguments:
  -h, --help         show this help message and exit
  -n, --dry          dry run on Salesforce
  -s SID, --sid SID  Salesforce SID Cookie (optional)
  -d, --debug        Enable debugging

If no email is specified, Salesforce will be queried for pending tasks
```

## Configuration

You need a `~/.canonicalrc` like so, it should be mode 600. Using a password manager is recommended, for example using 1Password and `--config <(op inject -i ~/.canonicalrc)`

```yaml
services:
  discourse:
    ubuntu:
      url: 'https://discourse.ubuntu.com' 
      username: 'your_username_here'
      key: 'your_api_key_here'
    snap:
      url: 'https://forum.snapcraft.io'
      username: 'your_username_here'
      key: 'your_api_key_here'
  indico:
    prod:
      url: 'https://events.canonical.com'
      key: 'your_indico_token_here'
tools:
  cangdpr:
    discourses:
      ubuntu:
        dataquery_gdpr_id: NNN          # This is the id of the data explorer query to look up all emails
      snap:
        dataquery_gdpr_id: NNN
    profile: "/optional/path/to/persistant/profile"
    binary: "/optional/path/to/specific/binary/of/firefox"
    geckodriver: "/optional/path/to/geckodriver"
```


For each discourse instance, you need to create a data explorer query that will look up all emails (also secondary).
* In the admin UI, go to Plugins -> Data Explorer
* Click on the + sign, enter gdpr_email_lookup as the name, then Create New
* Enter below SQL into the textbox
* Save and run, testing with an email address you know


```sql
-- [params]
-- string :email

SELECT u.id, u.username, ue.email
  FROM user_emails ue
  JOIN users u ON u.id = ue.user_id
 WHERE email = :email
```
