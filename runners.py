## -*- coding: utf-8 -*-
##
## runners.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     16 oktober 2012
## Copyright (c) 2012, Toke Høiland-Jørgensen
##
## This program is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program.  If not, see <http://www.gnu.org/licenses/>.

import threading, time, shlex, subprocess, re

class ProcessRunner(threading.Thread):
    """Default process runner for any process."""

    def __init__(self, binary, options, delay, *args, **kwargs):
        threading.Thread.__init__(self,*args, **kwargs)
        self.binary = binary
        self.options = options
        self.delay = delay
        self.result = None

    def run(self):
        """Runs the configured job. If a delay is set, wait for that many
        seconds, then open the subprocess, wait for it to finish, and collect
        the last word of the output (whitespace-separated)."""

        if self.delay:
            time.sleep(self.delay)
        args = [self.binary] + shlex.split(self.options)
        prog = subprocess.Popen(args,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         universal_newlines=True)
        out,err=prog.communicate()
        self.result = self.parse(out)

    def parse(self, output):
        """Default parser returns the last (whitespace-separated) word of
        output."""

        return output.split()[-1].strip()

DefaultRunner = ProcessRunner

class NetperfDemoRunner(ProcessRunner):
    """Runner for netperf demo mode."""

    def parse(self, output):
        """Parses the interim result lines and returns a list of (time,value)
        pairs."""

        result = []
        lines = output.split("\n")
        for line in lines:
            if line.startswith("Interim"):
                parts = line.split()
                result.append([float(parts[9]), float(parts[2])])

        return result

class PingRunner(ProcessRunner):
    """Runner for ping/ping6 in timestamped (-D) mode."""

    pingline_regex = re.compile(r'^\[([0-9]+\.[0-9]+)\].*time=([0-9]+(?:\.[0-9]+)?) ms$')

    def parse(self, output):
        result = []
        lines = output.split("\n")
        for line in lines:
            match = self.pingline_regex.match(line)
            if match:
                result.append([float(match.group(1)), float(match.group(2))])

        return result
