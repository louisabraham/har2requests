#!/usr/bin/env python3

from collections import namedtuple, deque
import json
import sys
import subprocess
import io
from functools import reduce, lru_cache
from datetime import datetime
from operator import attrgetter

import click

from .stringalg import longest_common_substring


# we look at the last responses to find the definition of a header
RESPONSE_LOOKUP = 5
# limit to the size of a response to be searched
MAX_SIZE = 100_000
# what size must be a header to be searched
SIZE_THRESHOLD = 16
# what fraction of a header must be present in a response
# to be matched
MATCH_FRACTION_THRESHOLD = 0.5


@lru_cache(50)
def match_wrapped(header, text):
    match_size = longest_common_substring(header, text)
    match_fraction = match_size / len(header)
    return match_fraction > MATCH_FRACTION_THRESHOLD


def match(header, text):
    if len(header) < SIZE_THRESHOLD:
        return
    if len(text) / len(header) < MATCH_FRACTION_THRESHOLD:
        return
    if not text:
        return
    return match_wrapped(header, text)


class Variable(str):
    """Variable class, used to shortcut the !r format"""

    def __repr__(self):
        return self


class Request(
    namedtuple(
        "Request", "method, url, cookies, headers, postData, responseText, datetime"
    )
):
    @staticmethod
    def from_json(request, response, startedDateTime):
        return Request(
            method=request["method"],
            url=request["url"],
            cookies=Request.dict_from_har(request["cookies"]),
            headers=Request.process_headers(Request.dict_from_har(request["headers"])),
            postData=Request.dict_from_har(request["postData"]["params"])
            if request["method"] in ["POST", "PUT"]
            else None,
            responseText=response["content"]["text"],
            datetime=Request.parse_datetime(startedDateTime),
        )

    @staticmethod
    def dict_from_har(j):
        """Build a dictionary from the names and values"""
        return {x["name"]: x["value"] for x in j}

    @staticmethod
    def parse_datetime(s):
        s = s[:-3] + s[-2:]
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z")

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
        print(
            f"r = requests.{self.method.lower()}({self.url!r},",
            f'    {f"cookies={self.cookies!r}," if self.cookies else ""}',
            f"""    {f"headers={'{'}**base_headers, {repr(headers)[1:]}," if self.headers else ""}""",
            f'    {f"json={self.postData!r}," if self.postData else ""}',
            ")",
            sep="\n",
            file=file,
        )


def dict_intersection(a: dict, b: dict):
    """Elements that are the same in a and b"""
    return {k: v for k, v in a.items() if k in b and b[k] == v}


def dict_change(a: dict, b: dict):
    """Elements of b that are not the same in a"""
    return {k: v for k, v in b.items() if k not in a or a[k] != v}


def dict_delete(a: dict, b: dict):
    """Elements that are in b but not in a"""
    return [k for k in a if k not in b]


def infer_headers_origin(requests, base_headers):
    """
    Returns:
        variables_to_bind : List[List[name, value]]
            variables_to_bind[i] is the list of variables
            defined by the i-th response
    """
    variables_to_bind = [[] for _ in range(len(requests))]
    header_to_variable = {}

    variable_names = set()

    def new_variable_name(base_name):
        """Find a new unused variable name
        """
        i = 1
        while f"{base_name}_{i}" in variable_names:
            i += 1
        variable_names.add(f"{base_name}_{i}")
        return f"{base_name}_{i}"

    responses_db = deque([], RESPONSE_LOOKUP)

    # for each header of each request,
    # try to match it in the responses_db
    for request_id, request in enumerate(requests):
        for header_key, value in request.headers.items():
            if header_key in base_headers:
                continue
            if value in header_to_variable:
                continue
            for response_id, text in responses_db:
                if match(value, text):
                    name = new_variable_name(header_key)
                    variables_to_bind[response_id].append((name, value))
                    header_to_variable[value] = name
        if SIZE_THRESHOLD <= len(request.responseText) <= MAX_SIZE:
            responses_db.append((request_id, request.responseText))

    return variables_to_bind


@click.command()
@click.argument("src", type=click.File(encoding="utf-8"))
def main(src):
    entries = json.load(src)["log"]["entries"]

    # read all requests
    requests = []
    for entry in entries:
        request = Request.from_json(
            entry["request"], entry["response"], entry["startedDateTime"]
        )
        requests.append(request)

    requests.sort(key=attrgetter("datetime"))

    # compute common headers
    base_headers = reduce(dict_intersection, (r.headers for r in requests))

    # detect origin of headers
    variables_to_bind = infer_headers_origin(requests, base_headers)

    # output through black
    proc = subprocess.Popen(
        ["black", "-"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    wrapper = io.TextIOWrapper(proc.stdin)

    # output headers
    print(f"base_headers = {base_headers!r}\n", file=wrapper)

    # output requests
    header_to_variable = {}
    for (request, variable_definitions) in zip(requests, variables_to_bind):
        request.dump(
            base_headers=base_headers,
            header_to_variable=header_to_variable,
            file=wrapper,
        )
        print("\n", file=wrapper)

        if variable_definitions:
            print(
                "# These variables probably come from the result of the request above",
                file=wrapper,
            )
            for (name, value) in variable_definitions:
                print(f"{name} = {value!r}", file=wrapper)
                header_to_variable[value] = name
            print("\n", file=wrapper)

    wrapper.flush()
    proc.stdin.close()
    proc.wait()


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    main()

