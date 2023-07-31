import json
from urllib.parse import urljoin

import requests
from pydiscourse import DiscourseClient
from pydiscourse.exceptions import DiscourseError


class CanDiscourseClient(DiscourseClient):
    def __init__(self, name, config, extradata):
        self.name = name
        super().__init__(
            config["url"], api_username=config["username"], api_key=config["key"]
        )
        self.extradata = extradata or {}

    def _jsonpost(self, path, data):
        return self._jsonrequest("POST", path, data)

    def _jsonrequest(self, verb, path, data):
        url = self.host + path

        headers = {
            "Api-Key": self.api_key,
            "Api-Username": self.api_username,
            "Content-Type": "application/json",
        }

        response = requests.request(
            verb,
            url,
            allow_redirects=False,
            timeout=self.timeout,
            json=data,
            headers=headers,
        )

        try:
            decoded = response.json()
        except ValueError:
            raise DiscourseError("failed to decode response", response=response)

        if "errors" in decoded:
            message = decoded.get("message")
            if not message:
                message = ",".join(decoded["errors"])
            raise DiscourseError(message, response=response)

        return decoded

    def create_api_key(self, username, description):
        data = {"key": {"username": username, "description": description}}

        keydata = self._jsonpost("/admin/api/keys", data=data)
        return keydata["key"]["key"]

    def get_api_keys(self):
        data = self._get("/admin/api/keys.json")
        return data["keys"]

    def group(self, group_name):
        data = self._get(f"/g/{group_name}.json")
        return data["group"]

    def group_add_user(self, group_id, username):
        return self._put(
            f"/groups/{group_id}/members.json", usernames=username, notify_users=False
        )

    def dataquery_gdpr_user(self, email):
        if "dataquery_gdpr_id" not in self.extradata:
            data = self.user_by_email(email)
            if len(data) == 0:
                return None

            return data[0]
        else:
            dqid = self.extradata["dataquery_gdpr_id"]
            resp = self._post(
                f"/admin/plugins/explorer/queries/{dqid}/run",
                params=json.dumps({"email": email}),
            )
            if not resp["success"]:
                raise Exception("Data query failed: " + str(resp))

            if len(resp["rows"]) == 0:
                return None

            uid, username, email = resp["rows"][0]
            return {"id": uid, "username": username, "email": email}

    def format_user(self, user):
        return urljoin(
            self.host, "/admin/users/{}/{}".format(user["id"], user["username"])
        )
