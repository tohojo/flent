Installing Flent
----------------
Installing Flent can be done in several ways, depending on your operating system:

- **Debian and Ubuntu:** ``apt install flent``.

- **Ubuntu pre-18.04:** Add the `tohojo/flent PPA <https://launchpad.net/~tohojo/+archive/ubuntu/flent>`_.

- **Arch Linux:** Install Flent from `the AUR <https://aur.archlinux.org/packages/flent>`_.

- **FreeBSD:**
  ``pkg install flent`` to install the package or ``cd /usr/ports/net/flent && make install`` to install the port.

- **Other Linux and OSX with Macbrew:** Install from the `Python Package Index <https://pypi.python.org/pypi/flent>`_:
  ``pip install flent``.

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
