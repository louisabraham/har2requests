[![Downloads](https://pepy.tech/badge/har2requests)](https://pepy.tech/project/har2requests) [![PyPI
version](https://badge.fury.io/py/har2requests.svg)](https://badge.fury.io/py/har2requests)

# har2requests

- Step 1: Interact with a website from your usual browser
- Step 2: automatically generate the Python code to replay your
  requests

## Motivation

To write bots in Python, the two main options are:

- [requests](https://github.com/kennethreitz/requests) to produce HTTP
  requests directly
- [selenium](https://github.com/SeleniumHQ/selenium) to control a web
  browser

Of course, requests bots are more stable but they require more daunting
work to reverse engineer the javascript code and reproduce every request
made by the client.

Discover har2requests\!

## Features

- Automatic requests code generation from a [HAR
  file](https://en.wikipedia.org/wiki/.har)
- Detection of the headers common to all requests and code
  factorization
- Clever inference on the origin of authorization headers
- Code formatting using [black](https://github.com/ambv/black)

## Installation

    pip install har2requests

## Usage

From Chrome or Firefox, go to the Network tab of the Developer Tools,
put the filters you want and export to HAR.

To read from a file:

    har2requests input.har > output.py

To read from the clipboard:

    pbpaste | har2requests - > output.py

By default, OPTIONS requests are ignored. To include them, use `--include-options`.

When encountering errors, you can use the `--unsafe` feature that will display warnings
instead of errors if the HAR file does not fit the specification.

`har2requests` uses string matching algorithms to find the origin of authorization headers. If your file is too big, it might be slow. You can disable it with `--no-infer`.

## Workflow tips

* `--exclude-cookie-headers` avoids the need to manually edit the output if all cookies are assigned by the website each session (the common scenario).
* `--generate-assertions` helps pinpoint unexpected variations quickly.
* `--debug-requests` helps if you need to debug the requests/responses themselves. 
