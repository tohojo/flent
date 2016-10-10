# -*- coding: utf-8 -*-
#
# test_parsers.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:      1 October 2016
# Copyright (c) 2016, Toke Høiland-Jørgensen
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

import unittest

from flent import runners

CAKE_1TIN = """qdisc cake 800c: dev ifb4eth0.3 root refcnt 2 bandwidth 250Mbit besteffort flows rtt 100.0ms raw
 Sent 69962090646 bytes 73766402 pkt (dropped 95, overlimits 54359263 requeues 0)
 backlog 0b 0p requeues 0
 memory used: 4148544b of 12500000b
 capacity estimate: 250Mbit
                 Tin 0
  thresh       250Mbit
  target         5.0ms
  interval     100.0ms
  pk_delay         3us
  av_delay         1us
  sp_delay         1us
  pkts        73766497
  bytes    69962229397
  way_inds     6061964
  way_miss     4161033
  way_cols           3
  drops             95
  marks            301
  sp_flows           1
  bk_flows           1
  max_len         1518
Time: 1475345872.910729727
"""

CAKE_3TINS = """qdisc cake 8011: dev eth0.3 root refcnt 2 bandwidth 100Mbit diffserv4 flows rtt 100.0ms raw
 Sent 1018642 bytes 1280 pkt (dropped 0, overlimits 268 requeues 0)
 backlog 0b 0p requeues 0
 memory used: 16576b of 5000000b
 capacity estimate: 100Mbit
                 Bulk   Best Effort      Video       Voice
  thresh       100Mbit   93750Kbit      75Mbit      25Mbit
  target         5.0ms       5.0ms       5.0ms       5.0ms
  interval     100.0ms     100.0ms     100.0ms     100.0ms
  pk_delay         0us       144us         1us         0us
  av_delay         0us        23us         0us         0us
  sp_delay         0us         1us         0us         0us
  pkts               0        1275           5           0
  bytes              0     1018166         476           0
  way_inds           0           0           0           0
  way_miss           0          65           2           0
  way_cols           0           0           0           0
  drops              0           0           0           0
  marks              0           0           0           0
  sp_flows           0           0           0           0
  bk_flows           0           1           0           0
  max_len            0        1518         172           0
Time: 1475345872.910729727
"""

QDISC_KEYS = ['backlog_bytes', 'backlog_pkts', 'backlog_requeues', 'dropped',
              'overlimits', 'requeues', 'sent_bytes', 'sent_pkts']


class TestParsers(unittest.TestCase):

    def check_res_keys(self, keys, res, raw_keys, raw):
        for k in keys:
            self.assertIn(k, res)
            self.assertIn(k, raw[0])
        for k in raw_keys:
            self.assertIn(k, raw[0])

    def new_runner(self, name):
        r = runners.get(name)
        return r(name='test', settings=object(), command='test',
                 delay=0, remote_host=None)

    def test_cake_parser(self):
        raw_keys = ["cake_%s" % k for k in runners.TcRunner.cake_keys]

        for data in (CAKE_1TIN, CAKE_3TINS):
            r = self.new_runner("tc")
            res = r.parse(data)
            self.check_res_keys(
                QDISC_KEYS + ['ecn_mark'], res, raw_keys, r.raw_values)

test_suite = unittest.TestLoader().loadTestsFromTestCase(TestParsers)
