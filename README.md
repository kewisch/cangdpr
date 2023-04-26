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
```
