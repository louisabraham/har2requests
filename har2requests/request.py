import warnings
from dataclasses import dataclass
from typing import Union
from datetime import datetime
import sys
from urllib.parse import urlsplit, urlunsplit

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
    responseText: str
    datetime: datetime

    @staticmethod
    def from_json(request, response, startedDateTime, unsafe=False):
        url = request["url"]
        if request.get("queryString", []):
            query = {a["name"]: a["value"] for a in request["queryString"]}
            url = urlunsplit(urlsplit(url)._replace(query=""))
        else:
            query = None

        postData = None
        if request["method"] in ["POST", "PUT"] and request["bodySize"] != 0:
            pd = request["postData"]
            params = "params" in pd
            text = "text" in pd

            POSTDATA_WARNING = (
                'You need exactly one of "params" or "text" in field postData'
            )
            if not unsafe:
                assert params + text == 1, POSTDATA_WARNING
            else:
                if params + text != 1:
                    warnings.warn(POSTDATA_WARNING + f"\n{request}\n{'-'*10}")
            if text:
                postData = pd["text"]
            if params:
                postData = Request.dict_from_har(pd["params"])

        req = Request(
            method=request["method"],
            url=url,
            query=query,
            cookies=Request.dict_from_har(request["cookies"]),
            headers=Request.process_headers(Request.dict_from_har(request["headers"])),
            postData=postData,
            responseText=response["content"].get("text", ""),
            datetime=dateutil.parser.parse(startedDateTime),
        )

        if response["content"]["size"] > 0 and not req.responseText:
            warnings.warn("content size > 0 but responseText is empty")

        return req

    @staticmethod
    def dict_from_har(j):
        """Build a dictionary from the names and values"""
        return {x["name"]: x["value"] for x in j}

    @staticmethod
    def process_headers(headers):
        headers = headers.copy()
        headers.pop("Content-Type", None)
        headers.pop("Content-Length", None)
        return headers

    def dump(self, base_headers=None, header_to_variable=None, file=sys.stdout):
        if base_headers is None:
            base_headers = {}
        if header_to_variable is None:
            header_to_variable = {}
        headers = dict_change(base_headers, self.headers)
        # display variable name instead of header
        for k, v in headers.items():
            if v in header_to_variable:
                headers[k] = Variable(header_to_variable[v])
        if headers:
            headers_string = f"headers={{**base_headers, {repr(headers)[1:]},"
        else:
            headers_string = "headers=base_headers"

        # previously, headers_string =
        # f"""{f"headers={{**base_headers, {repr(headers)[1:]}," if headers else ""}"""

        print(
            f"r = requests.{self.method.lower()}({self.url!r},",
            f'{f"params={self.query!r}," if self.query else ""}',
            f'{f"cookies={self.cookies!r}," if self.cookies else ""}',
            headers_string,
            f'{f"data={self.postData!r}," if self.postData else ""}',
            ")",
            sep="\n",
            file=file,
        )
