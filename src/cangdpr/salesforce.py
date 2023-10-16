import json
import logging
from collections import namedtuple
from urllib.parse import urljoin

import requests
from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait


class CanSalesforce:
    Record = namedtuple("SFRecord", "id,email")

    def __init__(
        self, company, gdpr_owner, sid=None, dry=False, profile=None, binary=None
    ):
        self.company = company
        self.gdpr_owner = gdpr_owner
        self.sid = sid
        self.dry = dry
        self.profile = profile
        self.binary = binary

    @property
    def base_url(self):
        return "https://{}.my.salesforce.com/services/data/v55.0/".format(self.company)

    @property
    def headers(self):
        self.ensure_sid()
        return {"Authorization": "Bearer " + self.sid}

    def _soql_query(self, query):
        soql_query_url = urljoin(self.base_url, "query")
        logging.debug("SOQL QUERY IS: " + query)
        return requests.get(soql_query_url, headers=self.headers, params={"q": query})

    def ensure_sid(self):
        if not self.sid:
            self.sid = self._get_sid_cookie()

    def _get_sid_cookie(self):
        def waiter(driver):
            return (
                driver.current_url
                == "https://{}.lightning.force.com/lightning/page/home".format(
                    self.company
                )
            )

        options = Options()

        if self.profile:
            profile = webdriver.FirefoxProfile(self.profile)
            options.profile = profile

        if self.binary:
            binary = FirefoxBinary(self.binary)
            options.binary = binary

        driver = webdriver.Firefox(options=options)
        wait = WebDriverWait(driver, 500)

        driver.get("https://{}.my.salesforce.com/".format(self.company))
        wait.until(waiter)

        driver.get("https://{}.my.salesforce.com/services/data/".format(self.company))
        sidcookie = driver.get_cookie("sid")

        driver.quit()

        logging.debug("SID Cookie is " + sidcookie["value"])

        return sidcookie["value"]

    def get_task_email(self, taskId):
        query = "SELECT Id, Email__c FROM Task WHERE OwnerId='{}' AND Subject LIKE '{} -%' LIMIT 1"
        r = self._soql_query(query.format(self.gdpr_owner, taskId))

        try:
            data = r.json()
        except json.decoder.JSONDecodeError as e:
            print(e)
            print(r.text)

        if isinstance(data, list) and len(data) > 0 and "errorCode" in data[0]:
            raise Exception("{}: {}".format(data[0]["errorCode"], data[0]["message"]))

        return data["records"][0]["Email__c"] if data["totalSize"] > 0 else None

    def get_tasks(self, since=None):
        if since:
            query = " ".join(
                [
                    f"SELECT Id,Subject,WhatId,Email__c FROM Task WHERE OwnerId='{self.gdpr_owner}' AND",
                    f"Status='Completed' AND CreatedDate = LAST_N_MONTHS:{since}",
                ]
            )

        else:
            query = "SELECT Id,Subject,WhatId,Email__c FROM Task WHERE OwnerId='{}' AND Status='Not Started'"

        r = self._soql_query(query.format(self.gdpr_owner))

        try:
            data = r.json()
        except json.decoder.JSONDecodeError as e:
            print(e)
            print(r.text)

        if isinstance(data, list) and len(data) > 0 and "errorCode" in data[0]:
            raise Exception("{}: {}".format(data[0]["errorCode"], data[0]["message"]))

        return map(
            lambda record: CanSalesforce.Record(record["Id"], record["Email__c"]),
            data["records"],
        )

    def mark_complete(self, taskId):
        if self.dry:
            return

        headers = self.headers.copy()
        headers["Content-Type"] = "application/json"
        task_url = urljoin(self.base_url, "sobjects/Task/{}".format(taskId))
        r = requests.patch(task_url, headers=headers, json={"Status": "Completed"})
        if r.status_code != 204:
            raise Exception("Could not mark task completed:\n" + r.text)

    def task_url(self, taskId):
        return "https://{}.lightning.force.com/lightning/r/Task/{}/view".format(
            self.company, taskId
        )
