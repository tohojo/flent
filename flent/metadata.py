# -*- coding: utf-8 -*-
#
# metadata.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     27 January 2014
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

import os
import re
import subprocess

from flent import util
from flent.loggers import get_logger

logger = get_logger(__name__)

TIMEOUT = 5
INTERESTING_OFFLOADS = ['tcp-segmentation-offload',
                        'udp-fragmentation-offload',
                        'large-receive-offload',
                        'generic-segmentation-offload',
                        'generic-receive-offload']

INTERESTING_SYSCTLS = ['net.core.rmem_max',
                       'net.core.wmem_max',
                       'net.ipv4.tcp_autocorking',
                       'net.ipv4.tcp_early_retrans',
                       'net.ipv4.tcp_ecn',
                       'net.ipv4.tcp_pacing_ca_ratio',
                       'net.ipv4.tcp_pacing_ss_ratio',
                       'net.ipv4.tcp_dsack',
                       'net.ipv4.tcp_fack',
                       'net.ipv4.tcp_sack',
                       'net.ipv4.tcp_fastopen',
                       'net.ipv4.tcp_syncookies',
                       'net.ipv4.tcp_window_scaling',
                       'net.ipv4.tcp_notsent_lowat',
                       'net.ipv4.tcp_limit_output_bytes',
                       'net.ipv4.tcp_timestamps',
                       'net.ipv4.tcp_congestion_control',
                       'net.ipv4.tcp_allowed_congestion_control',
                       'net.ipv4.tcp_available_congestion_control',
                       'net.ipv4.tcp_mem',
                       'net.ipv4.tcp_rmem',
                       'net.ipv4.tcp_wmem',
                       'net.ipv4.tcp_moderate_rcvbuf',
                       'net.ipv4.tcp_no_metrics_save']

# Modules we try to get versions for
INTERESTING_MODULES = ['cake',
                       'ath',
                       'ath9k',
                       'ath9k_common',
                       'ath9k_hw',
                       'mac80211',
                       'cfg80211']

try:
    processerror = subprocess.SubprocessError
except AttributeError:
    processerror = subprocess.CalledProcessError


class CommandRunner(object):

    def __init__(self):
        self.hostname = None
        self.env = os.environ.copy()
        self.fixup_path()

    def fixup_path(self):
        """Fix up the PATH to include /sbin and /usr/sbin since some of the
        utilities called (such as ip and tc) live here, and those directories
        are not normally in the path (on e.g. Debian)."""
        path = self.env['PATH'].split(':')
        if '/sbin' not in path:
            path.append('/sbin')
        if '/usr/sbin' not in path:
            path.append('/usr/sbin')
        self.env['PATH'] = ":".join(path)

    def set_hostname(self, hostname):
        self.hostname = hostname

    def __call__(self, command):
        """Try executing a command, and if successful,
        return the strip()'ed output, else None."""
        try:
            if self.hostname:
                logger.debug("Executing '%s' on host '%s'", command, self.hostname)
                command = "ssh %s '%s'" % (self.hostname, command)
            else:
                logger.debug("Executing '%s' on localhost", command)

            try:
                res = subprocess.check_output(command, universal_newlines=True,
                                              shell=True, stderr=subprocess.STDOUT,
                                              env=self.env, timeout=TIMEOUT)
            except TypeError:
                # Python 2 doesn't have timeout arg
                res = subprocess.check_output(command, universal_newlines=True,
                                              shell=True, stderr=subprocess.STDOUT,
                                              env=self.env)
            return res.strip()
        except processerror:
            return None


get_command_output = CommandRunner()

__all__ = ['record_metadata']


def record_metadata(results, extended, hostnames):
    logger.debug("Gathering local metadata")
    m = results.meta()
    get_command_output.set_hostname(None)
    m['KERNEL_NAME'] = get_command_output("uname -s")
    m['KERNEL_RELEASE'] = get_command_output("uname -r")
    m['MODULE_VERSIONS'] = get_module_versions()
    m['SYSCTLS'] = get_sysctls()
    m['EGRESS_INFO'] = get_egress_info(target=m['HOST'],
                                       ip_version=m['IP_VERSION'],
                                       extended=extended)

    if extended:
        m['IP_ADDRS'] = get_ip_addrs()
        m['GATEWAYS'] = get_gateways()
        m['WIFI_DATA'] = get_wifi_data()

    m['REMOTE_METADATA'] = {}

    for h in hostnames:
        logger.debug("Gathering remote metadata from %s", h)
        get_command_output.set_hostname(h)
        m['REMOTE_METADATA'][h] = {}
        m['REMOTE_METADATA'][h]['LOCAL_HOST'] = get_command_output("hostname")
        m['REMOTE_METADATA'][h]['KERNEL_NAME'] = get_command_output("uname -s")
        m['REMOTE_METADATA'][h]['KERNEL_RELEASE'] = get_command_output("uname -r")
        m['REMOTE_METADATA'][h]['MODULE_VERSIONS'] = get_module_versions()
        m['REMOTE_METADATA'][h]['SYSCTLS'] = get_sysctls()
        m['REMOTE_METADATA'][h]['EGRESS_INFO'] = get_egress_info(
            target=m['HOST'], ip_version=m['IP_VERSION'], extended=extended)

        if m['EGRESS_INFO'] is not None and 'src' in m['EGRESS_INFO']:
            m['REMOTE_METADATA'][h]['INGRESS_INFO'] = get_egress_info(
                target=m['EGRESS_INFO']['src'], ip_version=m['IP_VERSION'],
                extended=extended)
        else:
            m['REMOTE_METADATA'][h]['INGRESS_INFO'] = None
            m['REMOTE_METADATA'][h]['EGRESS_INFO'] = get_egress_info(
                target=m['HOST'], ip_version=m['IP_VERSION'],
                extended=extended)

        if extended:
            m['REMOTE_METADATA'][h]['IP_ADDRS'] = get_ip_addrs()
            m['REMOTE_METADATA'][h]['GATEWAYS'] = get_gateways()
            m['REMOTE_METADATA'][h]['WIFI_DATA'] = get_wifi_data()


def record_postrun_metadata(results, extended, hostnames):
    logger.debug("Recording postrun metadata")
    m = results.meta()
    get_command_output.set_hostname(None)
    if m['EGRESS_INFO'] is not None:

        m['EGRESS_INFO']['tc_stats_post'] = get_tc_stats(
            m['EGRESS_INFO']['iface'])

    for h in hostnames:
        get_command_output.set_hostname(h)
        for i in 'EGRESS_INFO', 'INGRESS_INFO':
            if m['REMOTE_METADATA'][h][i] is not None:
                m['REMOTE_METADATA'][h][i]['tc_stats_post'] = get_tc_stats(
                    m['REMOTE_METADATA'][h][i]['iface'])


def get_ip_addrs(iface=None):
    """Try to get IP addresses associated to this machine. Uses iproute2 if available,
    otherwise falls back to ifconfig."""
    addresses = {}

    cmd = "ip addr show"
    if iface is not None:
        cmd += " dev %s" % iface
    output = get_command_output(cmd)

    if output is None:
        cmd = "ifconfig"
        if iface is not None:
            cmd += " %s" % iface
        output = get_command_output(cmd)

    iface_re = re.compile('^([0-9]+: )?([a-z0-9-]+):')

    if output is not None:
        lines = output.splitlines()
        iface = None
        addrs = []
        for l in lines:
            # Both ifconfig and iproute2 emit addresses on lines starting with
            # the address identifier, and fields are whitespace-separated. Look
            # for that and parse accordingly.
            m = iface_re.match(l)
            if m is not None:
                if iface and addrs:
                    addresses[iface] = addrs
                iface = m.group(2)
                addrs = []
            parts = l.strip().split()
            if parts and parts[0] in ('inet', 'inet6'):
                a = parts[1]
                if '/' in a:  # iproute2 adds subnet qualification; strip that
                    a = a[:a.index('/')]
                if '%' in a:  # BSD may add interface qualification; strip that
                    a = a[:a.index('%')]
                addrs.append(a)
        if addrs and iface:
            addresses[iface] = addrs
    return addresses or None


def get_link_params(iface):
    link_params = {}
    output = get_command_output("ip link show dev %s" % iface)

    if output is None:
        output = get_command_output("ifconfig %s" % iface)

    if output is not None:
        m = re.search("(qlen|txqueuelen) (\d+)", output)
        if m:
            link_params['qlen'] = m.group(2)
        m = re.search("ether ([0-9a-f:]{17})", output)
        if m:
            link_params['ether'] = m.group(1)

    output = get_command_output("ethtool %s" % iface)
    if output is not None:
        m = re.search("Speed: ([0-9]+Mb/s)", output)
        if m:
            link_params['speed'] = m.group(1)
        m = re.search("Duplex: (\w+)", output)
        if m:
            link_params['duplex'] = m.group(1)

    return link_params or None


def get_offloads(iface):
    offloads = {}

    output = get_command_output("ethtool -k %s" % iface)
    val_map = {'on': True, 'off': False}
    if output is not None:
        for l in output.splitlines():
            parts = l.split()
            key = parts[0].strip(":")
            if key in INTERESTING_OFFLOADS:
                try:
                    offloads[key] = val_map[parts[1]]
                except KeyError:
                    continue
    return offloads or None


def get_gateways():
    gws = []
    # Linux netstat only outputs IPv4 data by default, but can be made to output
    # both if passed both -4 and -6
    output = get_command_output("netstat -46nr")
    if output is None:
        # If that didn't work, maybe netstat doesn't support -4/-6 (e.g. BSD),
        # so try without
        output = get_command_output("netstat -nr")
    if output is not None:
        output = output.replace("Next Hop", "Next_Hop")  # breaks part splitting
        lines = output.splitlines()
        iface_idx = None

        for line in lines:
            parts = line.split()
            if not parts:
                continue

            # Try to find the column header; should have "Destination" as first
            # word.
            if parts[0] == "Destination":
                # Linux uses Iface or If as header (for IPv4/6), FreeBSD uses If
                for n in ("Iface", "Netif", "If"):
                    if n in parts:
                        iface_idx = parts.index(n)
            if parts[0] in ("0.0.0.0", "default", "::/0"):
                if iface_idx is not None:
                    # The fields may run into each other in some instances; try
                    # to detect this, and if so just assume that the interface
                    # name is the last field (it often is, on Linux).
                    if iface_idx > len(parts) - 1:
                        iface_idx = -1
                    gw = {'ip': parts[1], 'iface': parts[iface_idx]}
                    if not gw['iface'].startswith('lo'):
                        gws.append(gw)
                else:
                    gws.append({'ip': parts[1]})
    return gws


def get_egress_info(target, ip_version, extended):
    route = {}

    if target:
        ip = util.lookup_host(target, ip_version)[4][0]
        output = get_command_output("ip route get %s" % ip)
        if output is not None:
            # Linux iproute2 syntax. Example:
            # $ ip r get 8.8.8.8
            # 8.8.8.8 via 10.109.3.254 dev wlan0  src 10.109.0.146
            #     cache
            parts = iter(output.split())
            for p in parts:
                if p == 'via':
                    route['nexthop'] = next(parts)
                elif p == 'dev':
                    route['iface'] = next(parts)
                elif p == 'src':
                    route['src'] = next(parts)
        else:
            output = get_command_output("route -n get %s" % ip)
            if output is not None:
                # BSD syntax. Example:
                # $ route -n get 8.8.8.8
                #    route to: 8.8.8.8
                # destination: default
                #        mask: default
                #     gateway: 10.42.7.225
                #   interface: em0
                #       flags: <UP,GATEWAY,DONE,STATIC>
                #  recvpipe  sendpipe  ssthresh  rtt,msec    mtu        weight    expire
                #        0         0         0         0      1500         1         0

                for line in output.splitlines():
                    if ":" not in line:
                        continue
                    k, v = [i.strip() for i in line.split(":")]
                    if k == "gateway":
                        route['nexthop'] = v
                    if k == "interface":
                        route['iface'] = v

    if route:
        route['qdiscs'] = get_qdiscs(route['iface'])
        route['tc_stats_pre'] = get_tc_stats(route['iface'])
        route['classes'] = get_classes(route['iface'])
        route['offloads'] = get_offloads(route['iface'])
        route['bql'] = get_bql(route['iface'])
        route['driver'] = get_driver(route['iface'])
        route['link_params'] = get_link_params(route['iface'])
        route['target'] = ip
        if 'nexthop' not in route:
            route['nexthop'] = None

        if not extended:
            for k in 'gateway', 'src', 'nexthop', 'target':
                if k in route:
                    del route[k]
            if route['link_params'] and 'ether' in route['link_params']:
                del route['link_params']['ether']

    return route or None


def parse_tc(cmd, kind):
    items = []

    output = get_command_output(cmd)
    if output is not None:
        lines = output.splitlines()
        for line in lines:
            if line.startswith(" "):
                itm = items[-1]
                if 'stats' in itm:
                    itm['stats'].append(line.strip())
                else:
                    itm['stats'] = [line.strip()]
                continue

            parts = line.split()
            if not parts or parts[0] != kind:
                continue
            item = {'name': parts[1],
                    'id': parts[2]}
            if parts[3] == 'root':
                item['parent'] = 'root'
                params = parts[4:]
            else:
                item['parent'] = parts[4]
                params = parts[5:]

            # Assume that the remainder of the output line is a set of space
            # delimited key/value pairs. Some qdiscs (e.g. fq_codel) has a
            # single non-valued parameter at the end, in which case the length
            # of params will be uneven. In this case an empty string is added as
            # the parameter "value", to make sure it is included.
            if len(params) % 2 > 0:
                params.append("")
            item['params'] = dict(zip(params[::2], params[1::2]))

            items.append(item)
    return items or None


def get_qdiscs(iface):
    return parse_tc("tc qdisc show dev %s" % iface, "qdisc")


def get_tc_stats(iface):
    output = get_command_output("tc -s qdisc show dev %s" % iface)
    items = []
    if output is not None:
        item = []
        # Split out output so we get one list entry for each qdisc -- first line
        # of a qdisc's stats output is non-indented, subsequent lines are
        # indented by spaces.
        for line in filter(None, output.splitlines()):
            if line.startswith(" "):
                item.append(line)
            else:
                if item:
                    items.append("\n".join(item))
                item = [line]
        if item:
            items.append("\n".join(item))
    return items or None


def get_classes(iface):
    return parse_tc("tc class show dev %s" % iface, "class")


def get_bql(iface):
    bql = []
    output = get_command_output(
        'for i in /sys/class/net/%s/queues/tx-*; do [ -d $i/byte_queue_limits ] '
        '&& echo -n "$(basename $i) " && cat $i/byte_queue_limits/limit_max; done'
        % iface)
    if output is not None:
        bql = dict([i.split() for i in output.splitlines()])

    return bql or None


def get_driver(iface):
    return get_command_output(
        "basename $(readlink /sys/class/net/%s/device/driver)" % iface)


def get_sysctls():
    sysctls = {}

    output = get_command_output("sysctl -e %s" % " ".join(INTERESTING_SYSCTLS))
    if output is not None:
        for line in output.splitlines():
            parts = line.split("=")
            if len(parts) != 2:
                continue
            k, v = [i.strip() for i in parts]
            try:
                sysctls[k] = int(v)
            except ValueError:
                sysctls[k] = v

    return sysctls


def get_module_versions():
    module_versions = {}
    modules = []

    output = get_command_output("find /sys/module -name .note.gnu.build-id")

    if output is not None:
        module_files = output.split()

        for f in module_files:
            if "/sections/" in f:
                continue
            m = f.replace("/sys/module/", "").split("/", 1)[0]
            if m in INTERESTING_MODULES:
                modules.append((m, f))

    if modules:

        # The hexdump output will be a string of hexadecimal values of the
        # concatenation of all the .note.gnu.build-id files.
        #
        # Each file starts with "040000001400000003000000474e5500" (0x474e550 is
        # "GNU\0"), so simply split on that to get the data we are interested in.
        version_strings = get_command_output(
            "hexdump -ve \"/1 \\\"%02x\\\"\" {}".format(
                " ".join([m[1] for m in modules])))

        if version_strings:
            for (m, f), v in zip(modules,
                                 version_strings.split(
                                     "040000001400000003000000474e5500")[1:]):
                module_versions[m] = v

    return module_versions


def get_wifi_data():
    wifi_data = {}

    unwanted_keys = ["Interface", "ifindex", "wdev", "wiphy"]

    output = get_command_output("iw dev")
    iface = None
    if output is not None:

        for line in output.splitlines():

            parts = line.split()
            if len(parts) < 2:
                continue

            k, v = parts[0], parts[1]

            if k == 'Interface':
                iface = v
                wifi_data[iface] = {}
                continue
            elif iface is None:
                continue

            if k in unwanted_keys:
                continue

            if k == 'txpower':
                v = float(v)

            if k == 'channel':
                # This condition will return a dict with all the values of the channel
                # With the input "channel 1 (2412 MHz), width: 20 MHz, center1: 2412 MHz"
                # the output will be {'addr':..., channel': {'band': 2462, 'center1': 2462, 'number': 11, 'width': 20}, 'ssid':...}
                v = {}
                v['number'] = int(parts[1])
                v['band'] = int(parts[2].strip("("))
                v['width'] = int(parts[5])
                v['center1'] = int(parts[8])

            if line.strip() == "multicast TXQ:":
                # No interesting output after this
                iface = None
                continue

            wifi_data[iface][k] = v

    return wifi_data
