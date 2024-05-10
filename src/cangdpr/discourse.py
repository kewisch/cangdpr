import json
from urllib.parse import urljoin

import requests
from pydiscourse import DiscourseClient
from pydiscourse.exceptions import DiscourseClientError, DiscourseError


class CanDiscourseClient(DiscourseClient):
    def __init__(self, name, config, extradata):
        self.name = name
        super().__init__(
            config["url"], api_username=config["username"], api_key=config["key"]
        )
        self.extradata = extradata or {}

    def _jsonpost(self, path, data):
        return self._jsonrequest("POST", path, data)

    def _jsonput(self, path, data):
        return self._jsonrequest("PUT", path, data)

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

    def revoke_api_key(self, keyid):
        self._post(f"/admin/api/keys/{keyid}/revoke")

    def group(self, group_name):
        data = self._get(f"/g/{group_name}.json")
        return data["group"]

    def add_group(
        self,
        group_name,
        full_name,
        bio="",
        usernames="",
        owner_usernames="",
        visibility_level=0,
        members_visibility_level=0,
        mentionable_level=0,
        messageable_level=0,
        primary_group=False,
        public_admission=False,
        public_exit=False,
    ):
        data = {
            "group": {
                "name": group_name,
                "full_name": full_name,
                "bio_raw": bio,
                "usernames": usernames,
                "owner_usernames": owner_usernames,
                "visibility_level": visibility_level,
                "members_visibility_level": members_visibility_level,
                "primary_group": primary_group,
                "public_admission": public_admission,
                "public_exit": public_exit,
                "mentionable_level": mentionable_level,
                "messageable_level": messageable_level,
            }
        }

        return self._jsonpost("/admin/groups.json", data=data)

    def group_add_user(self, group_id, username):
        return self._put(
            f"/groups/{group_id}/members.json", usernames=username, notify_users=False
        )

    def group_remove_user(self, group_id, username):
        return self._delete(
            f"/groups/{group_id}/members.json", usernames=username, notify_users=False
        )

    def data_explorer_queries(self):
        data = self._get("/admin/plugins/explorer/queries.json")
        return data["queries"]

    def data_explorer_create_query(self, name):
        data = {"query": {"name": name}}

        data = self._jsonpost("/admin/plugins/explorer/queries", data=data)
        return data["query"]

    def data_explorer_edit_query(self, query_id, sql, group_ids=None):
        data = {
            "query[sql]": sql,
        }

        if group_ids:
            data["query[group_ids][]"] = group_ids

        data = self._put(f"/admin/plugins/explorer/queries/{query_id}", **data)
        return data["query"]

    def grant_moderation(self, userid):
        return self._put(f"/admin/users/{userid}/grant_moderation")

    def dataquery_gdpr_user(self, email):
        fallback = True
        if "dataquery_gdpr_id" in self.extradata:
            fallback = False
            dqid = self.extradata["dataquery_gdpr_id"]
            try:
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
            except DiscourseClientError as e:
                if e.response.status_code == 404:
                    print(
                        f"Warning: {self.name} is configured for dataquery but the endpoint is 404"
                    )
                    fallback = True

        if fallback:
            data = self.user_by_email(email)
            if len(data) == 0:
                return None

            return data[0]

    def format_user(self, user):
        return urljoin(
            self.host, "/admin/users/{}/{}".format(user["id"], user["username"])
        )
