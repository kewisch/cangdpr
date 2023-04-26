from urllib.parse import urljoin

from pydiscourse import DiscourseClient


class CanDiscourseClient(DiscourseClient):
    def __init__(self, config):
        super().__init__(
            config["url"], api_username=config["username"], api_key=config["key"]
        )

    def format_user(self, user):
        return urljoin(
            self.host, "/admin/users/{}/{}".format(user["id"], user["username"])
        )
