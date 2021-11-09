import warnings
from dataclasses import dataclass
from typing import Union
from datetime import datetime
import sys
from urllib.parse import urlsplit, urlunsplit
import json
from http.client import _is_legal_header_name as is_legal_header_name

import dateutil.parser

from .utils import dict_change


class Variable(str):
    """Variable class, used to shortcut the !r format"""

    def __repr__(self):
        return self


@dataclass
class Request:
    method: str
    url: str
    query: dict
    cookies: dict
    headers: dict
    postData: Union[str, dict]
    isJson: bool
    responseStatus: int
    responseHeaders: dict
    responseText: str
    responseData: dict
    responseCookies: dict
    datetime: datetime

    @staticmethod
    def from_json(request, response, startedDateTime, exclude_cookie_headers):
        url = request["url"]
        if request.get("queryString", []):
            query = Request.dict_from_har(request["queryString"])
            url = urlunsplit(urlsplit(url)._replace(query=""))
        else:
            query = None

        postData = None
        isJson = False
        if request["method"] in ["POST", "PUT"] and request["bodySize"] != 0:
            pd = request["postData"]
            params = "params" in pd and pd["params"]
            text = "text" in pd and pd["text"]

            # if both are presents, only params will be used
            if text:
                postData = pd["text"]
                if pd["mimeType"] == "application/json":
                    postData = json.loads(postData)
                    isJson = True
            if params:
                postData = Request.dict_from_har(pd["params"])

        responseStatus = response["status"]
        responseText = response["content"].get("text", "")
        if (
            "application/json" in response["content"].get("mimeType", "")
            and responseText
        ):
            responseData = json.loads(responseText)
        else:
            responseData = None

        headers = Request.process_headers(Request.dict_from_har(request["headers"]))
        responseHeaders = Request.process_headers(Request.dict_from_har(response["headers"]))
        if exclude_cookie_headers:
            headers.pop("Cookie", None)

        req = Request(
            method=request["method"],
            url=url,
            query=query,
            cookies=Request.dict_from_har(request["cookies"]),
            headers=headers,
            postData=postData,
            isJson=isJson,
            responseStatus=responseStatus,
            responseHeaders=responseHeaders,
            responseText=responseText,
            responseData=responseData,
            responseCookies=Request.dict_from_har(response["cookies"]),
            datetime=dateutil.parser.parse(startedDateTime),
        )

        if response["content"].get("size", 0) and not req.responseText:
            warnings.warn("content size > 0 but responseText is empty")

        return req

    @staticmethod
    def dict_from_har(j):
        """Build a dictionary from the names and values"""
        return {x["name"]: x["value"] for x in j}

    @staticmethod
    def process_headers(headers):
        headers = {k: v for k, v in headers.items() if is_legal_header_name(k.encode("utf-8"))}
        headers.pop("Content-Type", None)
        headers.pop("Content-Length", None)
        return headers

    def dump(self, session_headers=None, header_to_variable=None, file=sys.stdout):
        if session_headers is None:
            session_headers = {}
        if header_to_variable is None:
            header_to_variable = {}
        headers = dict_change(session_headers, self.headers)
        # display variable name instead of header
        for k, v in headers.items():
            if v in header_to_variable:
                headers[k] = Variable(header_to_variable[v])
        if headers:
            headers_string = f"headers={repr(headers)},"
        else:
            headers_string = ""

        print(
            f"r = s.{self.method.lower()}({self.url!r},",
            f'{f"params={self.query!r}," if self.query else ""}',
            # cookies should be managed at the  session level
            # f'{f"cookies={self.cookies!r}," if self.cookies else ""}',
            headers_string,
            f"{'json' if self.isJson else 'data'}={self.postData!r},"
            if self.postData
            else "",
            ")",
            sep="\n",
            file=file,
        )
