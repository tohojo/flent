## -*- coding: utf-8 -*-
##
## metadata.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     27 januar 2014
## Copyright (c) 2014, Toke Høiland-Jørgensen
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

import sys, os, socket, subprocess, time

from netperf_wrapper import util


__all__ = ['record_extended_metadata']

def record_extended_metadata(results):
    m = results.meta()
    m['KERNEL_NAME'] = get_command_output("uname -s")
    m['KERNEL_RELEASE'] = get_command_output("uname -r")
    m['IP_ADDRS'] = get_ip_addrs()
    m['EGRESS_GWS'] = get_egress_gws()
    m['EGRESS_ROUTE'] = get_egress_route(target=m['HOST'])

    ifaces = []
    if m['EGRESS_ROUTE']:
        ifaces.append(m['EGRESS_ROUTE']['iface'])
    if m['EGRESS_GWS']:
        ifaces.extend([i['iface'] for i in m['EGRESS_GWS'] if 'iface' in i])
    m['IFACE_OFFLOADS'] = get_offloads(set(ifaces))


def get_command_output(command):
    """Try executing a command, and if successful,
    return the strip()'ed output, else None."""
    try:
        res = subprocess.check_output(command, universal_newlines=True, shell=True,
                                      stderr=subprocess.STDOUT)
        return res.strip()
    except subprocess.CalledProcessError:
        return None

def has_iproute2():
    return util.which("ip") is not None

def get_ip_addrs(iface=None):
    """Try to get IP addresses associated to this machine. Uses iproute2 if available,
    otherwise falls back to ifconfig."""
    if has_iproute2():
        cmd = "ip addr show"
        if iface is not None:
            cmd += " dev %s" % iface
    else:
        cmd = "ifconfig"
        if iface is not None:
            cmd += " %s" % iface
    output = get_command_output(cmd)
    addrs = []

    if output is not None:
        lines = output.splitlines()
        for l in lines:
            # Both ifconfig and iproute2 emit addresses on lines starting with the address
            # identifier, and fields are whitespace-separated. Look for that and parse
            # accordingly.
            parts = l.strip().split()
            if parts and parts[0] in ('inet', 'inet6'):
                a =  parts[1]
                if '/' in a: # iproute2 adds subnet qualification; strip that out
                    a = a[:a.index('/')]
                if '%' in a: # BSD may add interface qualification; strip that out
                    a = a[:a.index('%')]
                addrs.append(a)
    return addrs

def get_offloads(ifaces=None):
    offload_list = {}

    for iface in ifaces:
        offloads = {}
        output = get_command_output("ethtool -k %s" % iface)
        val_map = {'on': True, 'off': False}
        interesting_offloads = ['tcp-segmentation-offload',
                                'generic-segmentation-offload',
                                'generic-receive-offload']
        if output is not None:
            for l in output.splitlines():
                parts = l.split()
                key = parts[0].strip(":")
                if key in interesting_offloads:
                    try:
                        offloads[key] = val_map[parts[1]]
                    except KeyError:
                        continue
        offload_list[iface] = offloads
    return offload_list


def get_egress_gws():
    gws = []
    # Linux netstat only outputs IPv4 data by default, but can be made to output both
    # if passed both -4 and -6
    output = get_command_output("netstat -46nr")
    if output is None:
        # If that didn't work, maybe netstat doesn't support -4/-6 (e.g. BSD), so try
        # without
        output = get_command_output("netstat -nr")
    if output is not None:
        output = output.replace("Next Hop", "Next_Hop") # breaks part splitting
        lines = output.splitlines()
        iface_idx = None

        for line in lines:
            parts = line.split()
            if not parts:
                continue

            # Try to find the column header; should have "Destination" as first word.
            if parts[0] == "Destination":
                # Linux uses Iface or If as header (for IPv4/6), FreeBSD uses If
                for n in ("Iface", "Netif", "If"):
                    if n in parts:
                        iface_idx = parts.index(n)
            if parts[0] in ("0.0.0.0", "default", "::/0"):
                if iface_idx is not None:
                    gw = {'ip': parts[1], 'iface': parts[iface_idx]}
                    if not gw['iface'].startswith('lo'):
                        gws.append(gw)
                else:
                    gws.append({'ip': parts[1]})
    return gws

def get_egress_route(target):
    route = {}

    if target:
        ip = util.lookup_host(target)[4][0]
        output = get_command_output("ip route get %s" % ip)
        if output is not None:
            # Linux iproute2 syntax. Example:
            # $ ip r get 8.8.8.8
            # 8.8.8.8 via 10.109.3.254 dev wlan0  src 10.109.0.146
            #     cache
            parts = iter(output.split())
            for p in parts:
                if p == 'via':
                    route['ip'] = parts.next()
                if p == 'dev':
                    route['iface'] = parts.next()
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
                    if not ":" in line:
                        continue
                    k,v = [i.strip() for i in line.split(":")]
                    if k == "gateway":
                        route['ip'] = v
                    if k == "interface":
                        route['iface'] = v

    return route or None
