#!/usr/bin/env python3

from collections import Counter, deque
import json
import re
import sys
import subprocess
import io
from functools import partial, lru_cache
from operator import attrgetter
import traceback
from typing import List

import click
from tqdm import tqdm

from .stringalg import longest_common_substring
from .utils import dict_change, json_dfs
from .request import Request, Variable

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
def _match_wrapped(header, text):
    match_size = longest_common_substring(header, text)
    match_fraction = match_size / len(header)
    return match_fraction > MATCH_FRACTION_THRESHOLD


def match(header, text) -> bool:
    if len(header) < SIZE_THRESHOLD:
        return False
    if len(text) / len(header) < MATCH_FRACTION_THRESHOLD:
        return False
    if not text:
        return False
    return _match_wrapped(header, text)


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
        """Find a new unused variable name"""
        i = 1
        while f"{base_name}_{i}" in variable_names:
            i += 1
        variable_names.add(f"{base_name}_{i}")
        return f"{base_name}_{i}"

    responses_db = deque([], RESPONSE_LOOKUP)
    tried_headers = set()

    # for each key of each header of each request,
    # try to match it in the responses_db
    print("Inferring header origin. If it's slow, try --no-infer.", file=sys.stderr)
    for request_id, request in enumerate(tqdm(requests)):
        for header_key, value in request.headers.items():
            if header_key in base_headers:
                continue
            if value in header_to_variable:
                continue
            if value in tried_headers:
                continue
            tried_headers.add(value)
            for response_id, text in responses_db:
                if match(value, text):
                    name = new_variable_name(header_key)
                    variables_to_bind[response_id].append((name, value))
                    header_to_variable[value] = name
        if SIZE_THRESHOLD <= len(request.responseText) <= MAX_SIZE:
            responses_db.append((request_id, request.responseText))

    return variables_to_bind


def infer_session_headers(requests):
    n_requests = len(requests)
    count = Counter()
    record = [[] for _ in range(len(requests))]
    for i, r in reversed(list(enumerate(requests))):
        for k, v in r.headers.items():
            count[k] += 1
            count[k, v] += 1
            if count[k, v] > 1 and count[k, v] / count[k] > 0.5:
                record[i].append(k)

    ans = []
    headers = {}
    for i, (r, rec) in enumerate(zip(requests, record)):
        for k in rec:
            headers[k] = r.headers[k]
        for k in headers:
            if k in r.headers:
                count[k] -= 1
            elif count[k] / (n_requests - i) < 0.5:
                headers[k] = None
        ans.append(headers.copy())
    return ans


@click.command()
@click.argument("src", type=click.File(encoding="utf-8"))
@click.option("--unsafe", is_flag=True)
@click.option("--no-infer", is_flag=True)
@click.option("--hide-result", is_flag=True)
@click.option("--include-options", is_flag=True)
@click.option("--generate-assertions", is_flag=True)
@click.option("--exclude-cookie-headers", is_flag=True)
@click.option("--debug-requests", is_flag=True)
def main(src, unsafe, no_infer, hide_result, include_options, generate_assertions, exclude_cookie_headers, debug_requests):
    entries = json.load(src)["log"]["entries"]

    # read all requests
    requests: List[Request] = []
    for entry in entries:
        try:
            request = Request.from_json(
                entry["request"],
                entry["response"],
                entry["startedDateTime"],
                exclude_cookie_headers
            )
            if request.method != "OPTIONS" or include_options:
                requests.append(request)
        except Exception:
            print(f"Exception while parsing\n{entry}\n{'-'*10}", file=sys.stderr)
            if unsafe:
                traceback.print_exc()
            else:
                raise

    requests.sort(key=attrgetter("datetime"))

    # compute common headers
    all_session_headers = infer_session_headers(requests)

    # detect origin of headers
    # TODO: use variables for all long stuff but keep flagging
    if no_infer:
        variables_to_bind = [[] for _ in range(len(requests))]
    elif not all_session_headers:
        variables_to_bind = [[] for _ in range(len(requests))]
    else:
        variables_to_bind = infer_headers_origin(requests, all_session_headers[0])

    # output through black
    proc = subprocess.Popen(
        ["black", "-"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    wrapper = io.TextIOWrapper(proc.stdin)

    output = partial(print, file=wrapper)
    output("import requests")
    if debug_requests:
        output("""import logging

# Enabling debugging at http.client level (requests->urllib3->http.client)
# you will see the REQUEST, including HEADERS and DATA, and RESPONSE with HEADERS but without DATA.
# the only thing missing will be the response.body which is not logged.
try: # for Python 3
    from http.client import HTTPConnection
except ImportError:
    from httplib import HTTPConnection
HTTPConnection.debuglevel = 1

logging.basicConfig() # you need to initialize logging, otherwise you will not see anything from requests
logging.getLogger().setLevel(logging.DEBUG)
requests_log = logging.getLogger("urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True""")
    output("s = requests.Session()\n")

    # output headers
    current_session_headers = {}
    # output requests
    header_to_variable = {}
    for (request, session_headers, variable_definitions) in zip(
        requests, all_session_headers, variables_to_bind
    ):

        header_changes = dict_change(current_session_headers, session_headers)
        for k, v in header_changes.items():
            if v in header_to_variable:
                header_changes[k] = Variable(header_to_variable[v])

        if header_changes:
            output(f"s.headers.update({header_changes!r})\n")
        current_session_headers = session_headers

        # print diff s_headers, current_session_headers
        request.dump(
            session_headers=current_session_headers,
            header_to_variable=header_to_variable,
            file=wrapper,
        )
        if generate_assertions:
            output(
                f"assert r.status_code == {request.responseStatus}, f'Expected status {request.responseStatus} but was {{r.status_code}} for url \"{request.url}\"'"
            )

        if debug_requests:
            output('# request headers:')
            output("#"
                + json.dumps(request.headers, indent=2)
                .strip()
                .replace("\n", "\n# "))
            output('# request cookies:')
            output("#"
                + json.dumps(request.cookies, indent=2)
                .strip()
                .replace("\n", "\n# "))
            output('# response headers:')
            output("#"
                + json.dumps(request.responseHeaders, indent=2)
                .strip()
                .replace("\n", "\n# "))
            output('# response cookies:')
            output("#"
                + json.dumps(request.responseCookies, indent=2)
                .strip()
                .replace("\n", "\n# "))

        if generate_assertions:
            expected_cookie_names = set(list(k for k,v in request.cookies.items() if v != '') + list(request.responseCookies.keys()))
            for k in expected_cookie_names.copy():
                if k in request.responseCookies and request.responseCookies[k] == '':
                    expected_cookie_names.remove(k)
            expected_cookie_names_safe = str(list(map(lambda str: re.sub("'", "\\'", str), expected_cookie_names)))
            output(
                f"assert set({expected_cookie_names_safe}) == set(s.cookies.get_dict().keys()), f\"Expected defined cookies to be {expected_cookie_names_safe} but was {{s.cookies.get_dict().keys()}} for url \\\"{request.url}\\\"\""
            )

        if not hide_result and request.responseData:
            output(
                "#"
                + json.dumps(request.responseData, indent=2)
                .strip()
                .replace("\n", "\n# ")
            )
        output("\n")

        if variable_definitions:
            output(
                "# These variables probably come from the result of the request above",
            )
            for (name, value) in variable_definitions:
                definition = value
                for k, v in json_dfs(request.responseData):
                    if isinstance(v, str) and v in value and len(v) / len(value) > 0.5:
                        definition = Variable(
                            (
                                '"'
                                + value.replace(
                                    v, f'''" + r.json()["{'"]["'.join(k)}"] + "'''
                                )
                                + '"'
                            )
                            .replace('"" + ', "")
                            .replace(' + ""', "")
                        )
                        break
                output(
                    f"{name} = {definition!r}",
                )
                header_to_variable[value] = name
            output(
                "\n",
            )

    wrapper.flush()
    proc.stdin.close()
    proc.wait()


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    main()
