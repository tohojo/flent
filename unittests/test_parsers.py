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

CAKE_4TINS = """qdisc cake 8011: dev eth0.3 root refcnt 2 bandwidth 100Mbit diffserv4 flows rtt 100.0ms raw
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
  marks              0           0           1           0
  sp_flows           0           0           0           0
  bk_flows           0           1           0           0
  max_len            0        1518         172           0
Time: 1475345872.910729727
"""


CAKE_LONG = """qdisc cake 802b: root refcnt 2 bandwidth 5500Kbit diffserv3 dual-srchost nat wash rtt 100.0ms noatm overhead 14
 Sent 259071458 bytes 1023518 pkt (dropped 29, overlimits 613436 requeues 0)
 backlog 9084b 6p requeues 0
 memory used: 172480b of 4Mb
 capacity estimate: 5500Kbit
                 Bulk   Best Effort      Voice
  thresh     343744bit    5500Kbit    1375Kbit
  target        52.9ms       5.0ms      13.2ms
  interval     147.9ms     100.0ms      26.4ms
  pk_delay         0us      29.2ms       901us
  av_delay         0us       8.8ms        39us
  sp_delay         0us       896us        29us
  pkts               0     1020694        2859
  bytes              0   258722431      381549
  way_inds           0       12787           0
  way_miss           0        1668          46
  way_cols           0           0           0
  drops              0          29           0
  marks              0        4091           0
  sp_flows           0           0           0
  bk_flows           0           6           0
  un_flows           0           0           0
  max_len            0        7420         907

qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 2574788578 bytes 1836807 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1484778582.638085363
---
qdisc cake 802b: root refcnt 2 bandwidth 5500Kbit diffserv3 dual-srchost nat wash rtt 100.0ms noatm overhead 14
 Sent 259208426 bytes 1023614 pkt (dropped 29, overlimits 613725 requeues 0)
 backlog 10598b 7p requeues 0
 memory used: 172480b of 4Mb
 capacity estimate: 5500Kbit
                 Bulk   Best Effort      Voice
  thresh     343744bit    5500Kbit    1375Kbit
  target        52.9ms       5.0ms      13.2ms
  interval     147.9ms     100.0ms      26.4ms
  pk_delay         0us      31.0ms       901us
  av_delay         0us       9.8ms        39us
  sp_delay         0us       2.1ms        29us
  pkts               0     1020791        2859
  bytes              0   258860913      381549
  way_inds           0       12787           0
  way_miss           0        1668          46
  way_cols           0           0           0
  drops              0          29           0
  marks              0        4094           0
  sp_flows           0           0           0
  bk_flows           0           6           0
  un_flows           0           0           0
  max_len            0        7420         907

qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 2574793266 bytes 1836869 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1484778582.838003590
---
qdisc cake 802b: root refcnt 2 bandwidth 5500Kbit diffserv3 dual-srchost nat wash rtt 100.0ms noatm overhead 14
 Sent 259337976 bytes 1023707 pkt (dropped 29, overlimits 613987 requeues 0)
 backlog 4542b 3p requeues 0
 memory used: 172480b of 4Mb
 capacity estimate: 5500Kbit
                 Bulk   Best Effort      Voice
  thresh     343744bit    5500Kbit    1375Kbit
  target        52.9ms       5.0ms      13.2ms
  interval     147.9ms     100.0ms      26.4ms
  pk_delay         0us      27.7ms       901us
  av_delay         0us       9.8ms        39us
  sp_delay         0us       671us        29us
  pkts               0     1020880        2859
  bytes              0   258984407      381549
  way_inds           0       12787           0
  way_miss           0        1668          46
  way_cols           0           0           0
  drops              0          29           0
  marks              0        4098           0
  sp_flows           0           0           0
  bk_flows           0           6           0
  un_flows           0           0           0
  max_len            0        7420         907

qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 2574798798 bytes 1836943 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1484778583.038040365
---
qdisc cake 802b: root refcnt 2 bandwidth 5500Kbit diffserv3 dual-srchost nat wash rtt 100.0ms noatm overhead 14
 Sent 259476458 bytes 1023804 pkt (dropped 29, overlimits 614269 requeues 0)
 backlog 4542b 3p requeues 0
 memory used: 172480b of 4Mb
 capacity estimate: 5500Kbit
                 Bulk   Best Effort      Voice
  thresh     343744bit    5500Kbit    1375Kbit
  target        52.9ms       5.0ms      13.2ms
  interval     147.9ms     100.0ms      26.4ms
  pk_delay         0us      24.2ms       901us
  av_delay         0us       9.2ms        39us
  sp_delay         0us       912us        29us
  pkts               0     1020977        2859
  bytes              0   259122889      381549
  way_inds           0       12787           0
  way_miss           0        1668          46
  way_cols           0           0           0
  drops              0          29           0
  marks              0        4101           0
  sp_flows           0           2           0
  bk_flows           0           4           0
  un_flows           0           0           0
  max_len            0        7420         907

qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 2574804390 bytes 1837018 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1484778583.238006023
---
qdisc cake 802b: root refcnt 2 bandwidth 5500Kbit diffserv3 dual-srchost nat wash rtt 100.0ms noatm overhead 14
 Sent 259608884 bytes 1023897 pkt (dropped 29, overlimits 614516 requeues 0)
 backlog 4542b 3p requeues 0
 memory used: 172480b of 4Mb
 capacity estimate: 5500Kbit
                 Bulk   Best Effort      Voice
  thresh     343744bit    5500Kbit    1375Kbit
  target        52.9ms       5.0ms      13.2ms
  interval     147.9ms     100.0ms      26.4ms
  pk_delay         0us      19.1ms       901us
  av_delay         0us       7.9ms        39us
  sp_delay         0us       952us        29us
  pkts               0     1021070        2859
  bytes              0   259255315      381549
  way_inds           0       12787           0
  way_miss           0        1668          46
  way_cols           0           0           0
  drops              0          29           0
  marks              0        4101           0
  sp_flows           0           0           0
  bk_flows           0           4           0
  un_flows           0           0           0
  max_len            0        7420         907

qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 2574809262 bytes 1837083 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1484778583.438004751
---
qdisc cake 802b: root refcnt 2 bandwidth 5500Kbit diffserv3 dual-srchost nat wash rtt 100.0ms noatm overhead 14
 Sent 259747686 bytes 1024000 pkt (dropped 29, overlimits 614830 requeues 0)
 backlog 16654b 11p requeues 0
 memory used: 172480b of 4Mb
 capacity estimate: 5500Kbit
                 Bulk   Best Effort      Voice
  thresh     343744bit    5500Kbit    1375Kbit
  target        52.9ms       5.0ms      13.2ms
  interval     147.9ms     100.0ms      26.4ms
  pk_delay         0us      45.0ms       901us
  av_delay         0us       9.8ms        39us
  sp_delay         0us       2.2ms        29us
  pkts               0     1021181        2859
  bytes              0   259406229      381549
  way_inds           0       12787           0
  way_miss           0        1669          46
  way_cols           0           0           0
  drops              0          29           0
  marks              0        4103           0
  sp_flows           0           0           0
  bk_flows           0           6           0
  un_flows           0           0           0
  max_len            0        7420         907

qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 2574813935 bytes 1837140 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1484778583.638004248
---
qdisc cake 802b: root refcnt 2 bandwidth 5500Kbit diffserv3 dual-srchost nat wash rtt 100.0ms noatm overhead 14
 Sent 259884526 bytes 1024114 pkt (dropped 29, overlimits 615158 requeues 0)
 backlog 1514b 1p requeues 0
 memory used: 172480b of 4Mb
 capacity estimate: 5500Kbit
                 Bulk   Best Effort      Voice
  thresh     343744bit    5500Kbit    1375Kbit
  target        52.9ms       5.0ms      13.2ms
  interval     147.9ms     100.0ms      26.4ms
  pk_delay         0us      43.0ms       901us
  av_delay         0us      10.8ms        39us
  sp_delay         0us       1.3ms        29us
  pkts               0     1021285        2859
  bytes              0   259527929      381549
  way_inds           0       12787           0
  way_miss           0        1669          46
  way_cols           0           0           0
  drops              0          29           0
  marks              0        4109           0
  sp_flows           0           2           0
  bk_flows           0           3           0
  un_flows           0           0           0
  max_len            0        7420         907

qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 2574848921 bytes 1837227 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1484778583.838036153
---
qdisc cake 802b: root refcnt 2 bandwidth 5500Kbit diffserv3 dual-srchost nat wash rtt 100.0ms noatm overhead 14
 Sent 260009480 bytes 1024203 pkt (dropped 29, overlimits 615373 requeues 0)
 backlog 10598b 7p requeues 0
 memory used: 172480b of 4Mb
 capacity estimate: 5500Kbit
                 Bulk   Best Effort      Voice
  thresh     343744bit    5500Kbit    1375Kbit
  target        52.9ms       5.0ms      13.2ms
  interval     147.9ms     100.0ms      26.4ms
  pk_delay         0us      32.3ms       901us
  av_delay         0us       9.6ms        39us
  sp_delay         0us       1.5ms        29us
  pkts               0     1021380        2859
  bytes              0   259661967      381549
  way_inds           0       12787           0
  way_miss           0        1669          46
  way_cols           0           0           0
  drops              0          29           0
  marks              0        4110           0
  sp_flows           0           0           0
  bk_flows           0           4           0
  un_flows           0           0           0
  max_len            0        7420         907

qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 2574854021 bytes 1837295 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1484778584.038005470
---
qdisc cake 802b: root refcnt 2 bandwidth 5500Kbit diffserv3 dual-srchost nat wash rtt 100.0ms noatm overhead 14
 Sent 260147962 bytes 1024300 pkt (dropped 29, overlimits 615660 requeues 0)
 backlog 7570b 5p requeues 0
 memory used: 172480b of 4Mb
 capacity estimate: 5500Kbit
                 Bulk   Best Effort      Voice
  thresh     343744bit    5500Kbit    1375Kbit
  target        52.9ms       5.0ms      13.2ms
  interval     147.9ms     100.0ms      26.4ms
  pk_delay         0us      31.0ms       901us
  av_delay         0us       9.4ms        39us
  sp_delay         0us       1.3ms        29us
  pkts               0     1021475        2859
  bytes              0   259797421      381549
  way_inds           0       12787           0
  way_miss           0        1669          46
  way_cols           0           0           0
  drops              0          29           0
  marks              0        4112           0
  sp_flows           0           0           0
  bk_flows           0           5           0
  un_flows           0           0           0
  max_len            0        7420         907

qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 2574858677 bytes 1837357 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1484778584.238010022
---
qdisc cake 802b: root refcnt 2 bandwidth 5500Kbit diffserv3 dual-srchost nat wash rtt 100.0ms noatm overhead 14
 Sent 260283470 bytes 1024396 pkt (dropped 29, overlimits 615928 requeues 0)
 backlog 6056b 4p requeues 0
 memory used: 172480b of 4Mb
 capacity estimate: 5500Kbit
                 Bulk   Best Effort      Voice
  thresh     343744bit    5500Kbit    1375Kbit
  target        52.9ms       5.0ms      13.2ms
  interval     147.9ms     100.0ms      26.4ms
  pk_delay         0us      31.4ms       901us
  av_delay         0us      10.2ms        39us
  sp_delay         0us       2.7ms        29us
  pkts               0     1021570        2859
  bytes              0   259931415      381549
  way_inds           0       12787           0
  way_miss           0        1669          46
  way_cols           0           0           0
  drops              0          29           0
  marks              0        4116           0
  sp_flows           0           0           0
  bk_flows           0           5           0
  un_flows           0           0           0
  max_len            0        7420         907

qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 2574863501 bytes 1837421 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1484778584.438004833
---
qdisc cake 802b: root refcnt 2 bandwidth 5500Kbit diffserv3 dual-srchost nat wash rtt 100.0ms noatm overhead 14
 Sent 260412986 bytes 1024488 pkt (dropped 29, overlimits 616172 requeues 0)
 backlog 3028b 2p requeues 0
 memory used: 172480b of 4Mb
 capacity estimate: 5500Kbit
                 Bulk   Best Effort      Voice
  thresh     343744bit    5500Kbit    1375Kbit
  target        52.9ms       5.0ms      13.2ms
  interval     147.9ms     100.0ms      26.4ms
  pk_delay         0us      28.4ms       901us
  av_delay         0us       9.6ms        39us
  sp_delay         0us       424us        29us
  pkts               0     1021660        2859
  bytes              0   260057903      381549
  way_inds           0       12787           0
  way_miss           0        1669          46
  way_cols           0           0           0
  drops              0          29           0
  marks              0        4121           0
  sp_flows           0           2           0
  bk_flows           0           3           0
  un_flows           0           0           0
  max_len            0        7420         907

qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 2574869093 bytes 1837496 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1484778584.638003530
"""

INGRESS_OUTPUT = """qdisc htb 1: root refcnt 2 r2q 10 default 11 direct_packets_stat 0 direct_qlen 1000
 Sent 13843 bytes 62 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
qdisc fq 8052: parent 1:11 limit 10000p flow_limit 100p buckets 1024 orphan_mask 1023 quantum 3028 initial_quantum 15140 refill_delay 40.0ms
 Sent 13843 bytes 62 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
  6 flows (5 inactive, 0 throttled)
  0 gc, 0 highprio, 0 throttled
qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 12815 bytes 65 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1508235458.602528897
---
qdisc htb 1: root refcnt 2 r2q 10 default 11 direct_packets_stat 0 direct_qlen 1000
 Sent 13941 bytes 63 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
qdisc fq 8052: parent 1:11 limit 10000p flow_limit 100p buckets 1024 orphan_mask 1023 quantum 3028 initial_quantum 15140 refill_delay 40.0ms
 Sent 13941 bytes 63 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
  6 flows (5 inactive, 0 throttled)
  0 gc, 0 highprio, 0 throttled
qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 12899 bytes 66 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1508235458.802541376
---
qdisc htb 1: root refcnt 2 r2q 10 default 11 direct_packets_stat 0 direct_qlen 1000
 Sent 14039 bytes 64 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
qdisc fq 8052: parent 1:11 limit 10000p flow_limit 100p buckets 1024 orphan_mask 1023 quantum 3028 initial_quantum 15140 refill_delay 40.0ms
 Sent 14039 bytes 64 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
  6 flows (5 inactive, 0 throttled)
  0 gc, 0 highprio, 0 throttled
qdisc ingress ffff: parent ffff:fff1 ----------------
 Sent 12983 bytes 67 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
Time: 1508235459.002541779
---"""

QDISC_KEYS = ['backlog_bytes', 'backlog_pkts', 'backlog_requeues', 'dropped',
              'overlimits', 'requeues', 'sent_bytes', 'sent_pkts']


class TestParsers(unittest.TestCase):

    def check_res_keys(self, keys, res, raw_keys, raw):
        for k in keys:
            self.assertIn(k, res)
            self.assertIn(k, raw[0])
        for k in raw_keys:
            self.assertIn(k, raw[0])

    def check_vals(self, keys, res):
        for k in keys:
            vals = [i[1] > 0 for i in res[k]]
            self.assertTrue(any(vals))

    def new_runner(self, name):
        r = runners.get(name)
        return r(name='test', settings=object(), command='test',
                 delay=0, remote_host=None, interface=None, interval=0,
                 length=0)

    def test_cake_parser(self):
        raw_keys = ["cake_%s" % k for k in runners.TcRunner.cake_keys]
        check_keys = ['sent_bytes', 'sent_pkts']

        for data in (CAKE_1TIN, CAKE_4TINS, CAKE_LONG):
            r = self.new_runner("tc")
            res = r.parse(data)
            self.check_res_keys(
                QDISC_KEYS + ['ecn_mark'], res, raw_keys, r.raw_values)
            if data == CAKE_LONG:
                self.check_vals(check_keys + ['ecn_mark'], res)
            else:
                self.check_vals(check_keys, res)

    def test_ingress_parser(self):
        r = self.new_runner("tc")
        res = r.parse(INGRESS_OUTPUT)
        self.check_res_keys(QDISC_KEYS, res, [], r.raw_values)
        self.check_vals(['sent_bytes', 'sent_pkts'], res)


test_suite = unittest.TestLoader().loadTestsFromTestCase(TestParsers)
