import json
from urllib.parse import urljoin

from pydiscourse import DiscourseClient


class CanDiscourseClient(DiscourseClient):
    def __init__(self, config, extradata):
        super().__init__(
            config["url"], api_username=config["username"], api_key=config["key"]
        )
        self.extradata = extradata

    def dataquery_gdpr_user(self, email):
        if "dataquery_gdpr_id" not in self.extradata:
            raise Exception(f"Missing dataquery_gdpr_id in {self.host} config")

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
