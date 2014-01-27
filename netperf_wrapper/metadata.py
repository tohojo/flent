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
    m['IFACE_OFFLOADS'] = get_offloads()


def get_command_output(command):
    """Try executing a command, and if successful,
    return the strip()'ed output, else None."""
    try:
        res = subprocess.check_output(command, universal_newlines=True, shell=True)
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
            if parts[0] in ('inet', 'inet6'):
                a =  parts[1]
                if '/' in a: # iproute2 adds subnet qualification; strip that out
                    a = a[:a.index('/')]
                addrs.append(a)
    return addrs

def get_offloads(iface=None):
    offloads = {}
    if iface is None:
        return offloads
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
    return offloads
