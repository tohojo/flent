Flent: The FLExible Network Tester
==================================

Flent is a Python wrapper to run multiple simultaneous netperf/iperf/ping
instances and aggregate the results. It was previously known as
'netperf-wrapper'. See the web site for the main documentation:
https://flent.org.

Installing Flent
----------------
Installing Flent can be done in several ways, depending on your operating system:

- **FreeBSD users:**
  ``pkg install flent`` to install the package or ``cd /usr/ports/net/flent && make install`` to install the port.

- **Ubuntu users:** Add the `tohojo/flent PPA <https://launchpad.net/~tohojo/+archive/ubuntu/flent>`_.

- **Debian users:** Use the `package included in Debian
  Stretch <https://packages.debian.org/stretch/flent>`_ and later.

- **Arch Linux users:** Install Flent from `the AUR <https://aur.archlinux.org/packages/flent>`_.

- **Other Linux and OSX with Macbrew:** Install from the `Python Package Index <https://pypi.python.org/pypi/flent>`_:
  ``pip install flent``.


Quick Start
-----------

See https://flent.org/intro.html#quick-start or doc/quickstart.rst.
