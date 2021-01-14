Flent: The FLExible Network Tester
==================================

Flent is a Python wrapper to run multiple simultaneous netperf/iperf/ping
instances and aggregate the results. It was previously known as
'netperf-wrapper'. See the web site for the main documentation:
https://flent.org.

Installing Flent
----------------
Installing Flent can be done in several ways, depending on your operating system:


- **Debian and Ubuntu:**

    .. code-block:: bash

      apt install flent

- **Fedora:**

    .. code-block:: bash

      dnf install flent

- **Ubuntu pre-18.04:**

  Add the `tohojo/flent PPA <https://launchpad.net/~tohojo/+archive/ubuntu/flent>`_.

- **Arch Linux:**

  Install Flent from `the AUR <https://aur.archlinux.org/packages/flent>`_.

- **Other Linux:**

  Install from the `Python Package Index <https://pypi.python.org/pypi/flent>`_:
  
    .. code-block:: bash

      pip install flent

- **FreeBSD:**

  Install the package

    .. code-block:: bash

      pkg install flent

  Or install the port
  
    .. code-block:: bash

        cd /usr/ports/net/flent && make install

- **macOS:**

  `Homebrew <https://brew.sh/>`_ and Python 3 must be installed (Python 3 can be installed using Homebrew)

  Install the `patched netperf package <https://github.com/kris-anderson/homebrew-netperf>`_

    .. code-block:: bash

      brew tap kris-anderson/netperf
      brew install netperf-enable-demo

  Install other dependencies

    .. code-block:: bash

      brew install fping
      pip3 install matplotlib --user

  Install Flent using pip

    .. code-block:: bash

      pip3 install flent --user

  Optional (install this if you want to use `flent-gui`)

    .. code-block:: bash

      pip3 install pyqt5 qtpy --user

Quick Start
-----------

See https://flent.org/intro.html#quick-start or doc/quickstart.rst.
