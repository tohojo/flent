## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add netstat output to a test

NETSTAT_HOSTS=TEST_PARAMETERS.get('netstat_hosts')
if NETSTAT_HOSTS:
    for host in NETSTAT_HOSTS.split(","):
        DATA_SETS['netstat_%s' % host] = {'interval': STEP_SIZE, 'length': TOTAL_LENGTH, 'host': host, 'units':
                                          'misc', 'runner': 'netstat'}
