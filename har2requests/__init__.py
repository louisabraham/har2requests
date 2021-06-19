#!/usr/bin/env python3

from collections import deque
import json
import sys
import subprocess
import io
from functools import partial, reduce, lru_cache
from operator import attrgetter
import traceback

import click
from tqdm import tqdm

from .stringalg import longest_common_substring
from .utils import dict_intersection
from .request import Request

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


@click.command()
@click.argument("src", type=click.File(encoding="utf-8"))
@click.option("--unsafe", is_flag=True)
@click.option("--no-infer", is_flag=True)
@click.option("--include-options", is_flag=True)
def main(src, unsafe, no_infer, include_options):
    entries = json.load(src)["log"]["entries"]

    # read all requests
    requests = []
    for entry in entries:
        try:
            request = Request.from_json(
                entry["request"],
                entry["response"],
                entry["startedDateTime"],
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
    # TODO: use increasing list of base_headers
    # TODO: new headers should be used at least twice
    # TODO? cluster remaining headers
    base_headers = reduce(dict_intersection, (r.headers for r in requests))

    # detect origin of headers
    # TODO: use variables for all long stuff but keep flagging
    # TODO: get path of longest string in JSON
    if no_infer:
        variables_to_bind = [[] for _ in range(len(requests))]
    else:
        variables_to_bind = infer_headers_origin(requests, base_headers)

    # output through black
    proc = subprocess.Popen(
        ["black", "-"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    wrapper = io.TextIOWrapper(proc.stdin)

    output = partial(print, file=wrapper)
    output("import requests")
    output("s = requests.Session()\n")

    # output headers
    output(f"s.headers.update({base_headers!r})\n")

    # output requests
    header_to_variable = {}
    for (request, variable_definitions) in zip(requests, variables_to_bind):
        request.dump(
            base_headers=base_headers,
            header_to_variable=header_to_variable,
            file=wrapper,
        )
        output("\n")

        if variable_definitions:
            output(
                "# These variables probably come from the result of the request above",
            )
            for (name, value) in variable_definitions:
                output(
                    f"{name} = {value!r}",
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
