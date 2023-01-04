# cangdpr

Tool to automate GDPR lookups on the Community Team at Canonical. Gets the job done.

## Usage

```
git clone https://github.com/kewisch/cangdpr
cd cangdpr
pipenv install
pipenv run gdpr --help
```

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

You need a `~/.canonicalrc` file that has `chmod 400`. It is yaml with the following content:

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
