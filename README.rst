har2requests
============

-  Step 1: Interact with a website from your usual browser
-  Step 2: automatically generate the Python code to replay your
   requests

Motivation
----------

To write bots in Python, the two main options are:

-  `requests <https://github.com/kennethreitz/requests>`__ to produce
   HTTP requests directly
-  `selenium <https://github.com/SeleniumHQ/selenium>`__ to control a
   web browser

Of course, requests bots are more stable but they require more daunting
work to reverse engineer the javascript code and reproduce every request
made by the client.

Discover har2requests!

Features
--------

-  Automatic requests code generation from a `HAR
   file <https://en.wikipedia.org/wiki/.har>`__
-  Detection of the headers common to all requests and code
   factorization
-  Clever inference on the origin of authorization headers
-  Code formatting using `black <https://github.com/ambv/black>`__

Installation
------------

::

   pip install har2requests

Usage
-----

From Chrome or Firefox, go to the Network tab of the Developer Tools,
put the filters you want and export to HAR.

To read from a file:

::

   har2requests input.har > output.py

To read from the clipboard:

::

   pbpaste | har2requests - > output.py

TODO
====

-  Use requests.Session
-  Handle cookies (e.g. with a session)
-  handle text field from post requests
