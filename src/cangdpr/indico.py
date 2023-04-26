import json
import sys
from urllib.parse import urljoin

import requests


class Indico:
    def __init__(self, config):
        self.base = config["url"]
        self.token = config["key"]

    def user_by_email(self, email):
        headers = {"Authorization": "Bearer " + self.token}
        data = {"email": email, "exact": "true"}

        r = requests.get(
            urljoin(self.base, "/user/search/"),
            headers=headers,
            params=data,
            allow_redirects=False,
        )
        if "location" in r.headers and "/login/" in r.headers["location"]:
            print("Your token has expired")
            sys.exit(1)

        try:
            data = r.json()
        except json.decoder.JSONDecodeError as e:
            print(e)
            print(r.text)

        if data["total"] > 0:
            return data["users"]
        else:
            return None

    def format_user(self, user):
        return urljoin(self.base, "/user/{}/profile/".format(user["id"]))
