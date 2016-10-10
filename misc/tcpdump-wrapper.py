# -*- coding: utf-8 -*-
#
# tcpdump-wrapper.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     30 April 2014
# Copyright (c) 2014-2016, Toke Høiland-Jørgensen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import absolute_import, division, print_function, unicode_literals

import optparse
import os
import shutil
import socket
import subprocess
import sys
import time

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256

DEFAULT_IFACE = 'eth1'
DEFAULT_SIZE = 128
DEFAULT_DEST_DIR = "/home/data"
CAPTURE_DIR = "/tmp"

parser = optparse.OptionParser(
    description="Wrapper to start/stop tcpdump.",
    usage="Usage: %prog [options] <start|stop> <filename>")

parser.add_option('-i', '--interface', action='store',
                  type="string", dest='INTERFACE', default=DEFAULT_IFACE)
parser.add_option('-s', '--size', action='store', type="int",
                  dest='SIZE', default=DEFAULT_SIZE)
parser.add_option('-d', '--dest-dir', action='store',
                  type="string", dest='DEST_DIR', default=DEFAULT_DEST_DIR)


def start_tcpdump(filename, iface=DEFAULT_IFACE, size=DEFAULT_SIZE):
    pidfile = os.path.join(CAPTURE_DIR, "%s.pid" % filename)
    if os.path.exists(pidfile):
        sys.stderr.write("Pidfile already exists: %s.\n" % pidfile)
        sys.exit(1)
    args = ['sudo', 'tcpdump', '-n', '-i', iface, '-s',
            str(size), '-w', os.path.join(CAPTURE_DIR, "%s.cap" % filename)]
    pid = os.fork()
    if pid:
        with open(pidfile, "w") as fp:
            fp.write("%d\n" % pid)
        sys.exit(0)
    else:
        logfile = os.path.join(CAPTURE_DIR, "%s.log" % filename)
        fp_in = open("/dev/null", "r")
        fp_out = open(logfile, "a")
        os.dup2(fp_in.fileno(), 0)
        os.dup2(fp_out.fileno(), 1)
        os.dup2(fp_out.fileno(), 2)
        os.closerange(3, MAXFD)
        prog = args[0]
        os.execvp(prog, args)


def stop_tcpdump(filename, dest_dir=DEFAULT_DEST_DIR):
    pidfile = os.path.join(CAPTURE_DIR, "%s.pid" % filename)
    logfile = os.path.join(CAPTURE_DIR, "%s.log" % filename)
    datafile = os.path.join(CAPTURE_DIR, "%s.cap" % filename)
    dest_data = os.path.join(dest_dir, "%s.cap.gz" % filename)
    dest_log = os.path.join(dest_dir, "%s.log" % filename)
    try:
        with open(pidfile, "r") as fp:
            pid = int(fp.read())
    except (OSError, IOError, ValueError) as e:
        sys.stderr.write("Unable to read pidfile: %s.\n" % e)
        sys.exit(1)

    try:
        subprocess.check_call("sudo kill %d" % pid, shell=True)
        os.unlink(pidfile)
    except subprocess.CalledProcessError as e:
        sys.stderr.write("Unable to kill: %s.\n" % e)

    if os.path.exists(dest_data) or os.path.exists(dest_log):
        sys.stderr.write(
            "Destination data or log file already exists. Not copying.\n")
        sys.exit(1)

    if not os.path.exists(dest_dir):
        try:
            os.mkdir(dest_dir)
        except OSError as e:
            sys.stderr.write("Unable to create destination directory: %s.\n" % e)
            sys.exit(1)

    time.sleep(0.5)

    shutil.copyfile(logfile, dest_log)
    try:
        if os.path.exists(datafile):
            subprocess.check_call("gzip -c %s > %s" %
                                  (datafile, dest_data), shell=True)
    except subprocess.CalledProcessError as e:
        sys.stderr.write("Unable to compress data file: %s.\n" % e)

    try:
        subprocess.check_call("sudo rm -f %s %s" %
                              (datafile, logfile), shell=True)
    except subprocess.CalledProcessError as e:
        sys.stderr.write("Unable to remove data and log files: %s.\n" % e)


if __name__ == "__main__":
    options, args = parser.parse_args()
    if len(args) != 2:
        parser.error("Need action and filename.")
    action, filename = args

    filename = "%s.%s" % (filename, socket.gethostname())

    if action == 'start':
        start_tcpdump(filename, iface=options.INTERFACE, size=options.SIZE)
    elif action == 'stop':
        stop_tcpdump(filename, dest_dir=options.DEST_DIR)
    else:
        parser.error("Unknown action: %s." % action)
