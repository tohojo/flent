Introduction
============

Flent is a wrapper around *netperf* and similar tools to run predefined
tests and aggregate and plot the results. It defines several tests that
can be run against one or more hosts, primarily targeted at testing for
the presence of bufferbloat under various conditions.

The aggregated data is saved in (gzipped) JSON format for later
processing and/or import into other tools. The JSON format is documented
below.

Apart from the JSON format, the data can be output as csv values, emacs
org mode tables or plots. Each test can specify several different plots,
including time-series plots of the values against each other, as well as
CDF plots of (e.g.) ping times.

Plots can be output to the formats supported by matplotlib by specifying
the output filename with :option:`-o` *output.{png,ps,pdf,svg}*. If no output
file is specified, the plot is diplayed using matplotlib’s interactive
plot browser, which also allows saving of the output (in .png format).

Installing Flent
----------------
Installing Flent can be done in several ways, depending on your operating system:

- **Debian and Ubuntu users:** Use the `packages from the Open Build Service
  <https://software.opensuse.org/download.html?project=home:tohojo:flent&package=flent>`_

- **Arch Linux users:** Install 'flent' from the AUR.

- **Other Linux and OSX with Macbrew:** Install from the Python cheese shop:
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
