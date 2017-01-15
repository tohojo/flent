# -*- coding: utf-8 -*-
#
# iperf-server.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     26 november 2012
# Copyright (c) 2012-2016, Toke Høiland-Jørgensen
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

import copy
import csv
import json
import subprocess
import threading
import time

iperf_cols = [
    'timestamp',
    'server_host',
    'server_port',
    'client_host',
    'transfer_id',
    'start_time',
    'time_interval',
    'total_length',
    'speed',
    'jitter',
    'errors',
    'datagrams',
    'error_percent',
    'out_of_order',
]

TIMEOUT = 10.0


class IperfReader(csv.DictReader):

    def __init__(self, csvfile):
        csv.DictReader.__init__(self, csvfile, fieldnames=iperf_cols)


def line_iterator(fp):
    line = fp.readline()
    while line:
        yield line
        line = fp.readline()


class TestData(object):

    def __init__(self, r_id):
        self._id = r_id
        self._last_update = time.time()
        self._records = []

    def add_record(self, record):
        self._records.append(record)
        self._last_update = time.time()

    def expired(self):
        return time.time() - self._last_update > TIMEOUT

    def records(self):
        return copy.deepcopy(self._records)


class Monitor(threading.Thread):

    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self, *args, **kwargs)
        self._test_data = {}
        self._lock = threading.RLock()

    def run(self):

        prog = subprocess.Popen(['iperf', '-s', '-u', '-i', '0.5', '-y', 'c'],
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=None,
                                universal_newlines=True)
        prog.stdin.close()
        reader = IperfReader(line_iterator(prog.stdout))

        for record in reader:
            self.handle_record(record)

    def handle_record(self, record):
        parts = record['time_interval'].split("-")
        length = float(parts[1]) - float(parts[0])

        # too long interval, this is a summary record
        if length > 2:
            return

        r_id = record['transfer_id']

        self._lock.acquire()
        if r_id not in self._test_data:
            self._test_data[r_id] = TestData(r_id)
        self._test_data[r_id].add_record(record)
        self._lock.release()

        self.collect_garbage()

    def collect_garbage(self):
        self._lock.acquire()
        for k, v in list(self._test_data.items()):
            if v.expired():
                del self._test_data[k]
        self._lock.release()

    def get_records(self, r_id):
        self._lock.acquire()
        try:
            return self._test_data[r_id].records()
        finally:
            self._lock.release()


monitor = Monitor()
monitor.start()

while True:
    try:
        request_id = input().strip()
        print(json.dumps(monitor.get_records(request_id)))
    except KeyError:
        print("No records for id %s." % request_id)
