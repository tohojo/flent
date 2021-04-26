Installing Flent
----------------
Installing Flent can be done in several ways, depending on your operating system:


- **Debian and Ubuntu:**

    .. code-block:: bash

      apt install flent

- **Fedora:**

    .. code-block:: bash

      dnf install flent

- **Gentoo:**

    .. code-block:: bash

      emerge net-analyzer/flent

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

Quick start
-----------
You must run netperf on two computers - a **server** and a **client**.

#. **Server (Computer 1):** Netperf needs to be started in "server mode" to
   listen for commands from the Client. To do this, install netperf on the
   Server computer, then enter:

   ``netserver &``

   *Note:* Instead of installing netperf on a local server, you may substitute
   the netserver that is running on netperf.bufferbloat.net by using :option:`-H
   netperf.bufferbloat.net<-H>` in the commands below.

   List of public hosts you can test against:

   - netperf.bufferbloat.net (also called netperf-east.bufferbloat.net)
   - netperf-west.bufferbloat.net
   - netperf-eu.bufferbloat.net

#. **Client (Computer 2):** Install netperf, then install flent on your Client
   computer. When you invoke flent on the Client, it will connect to the
   specified netserver (:option:`-H`) and carry out the measurements. Here are some useful
   commands:

   - RRUL: Create the standard graphic image used by the Bufferbloat project to
     show the down/upload speeds plus latency in three separate charts::

          flent rrul -p all_scaled -l 60 -H address-of-netserver -t text-to-be-included-in-plot -o filename.png

   - CDF: A Cumulative Distribution Function plot showing the probability that
     ping times will be below a bound::

          flent rrul -p ping_cdf -l 60 -H address-of-netserver -t text-to-be-included-in-plot -o filename.png

   - TCP Upload: Displays TCP upload speed and latency in two charts::

          flent tcp_upload -p totals -l 60 -H address-of-netserver -t text-to-be-included-in-plot -o filename.png

   - TCP Download: Displays TCP download speeds and latency in two charts::

          flent tcp_download -p totals -l 60 -H address-of-netserver -t text-to-be-included-in-plot -o filename.png

The output of each of these commands is a graphic (PNG) image along with a data
file in the current working directory that can be used to re-create the plot,
either from the command line (see :doc:`options`), or by loading them into the
GUI. Run :command:`flent-gui` to start the GUI.
