## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add netstat output to a test

NETSTAT_HOSTS=get_test_parameter('netstat_hosts', default=[], split=True)
for host in NETSTAT_HOSTS:
    DATA_SETS['netstat_%s' % host] = {'interval': STEP_SIZE,
                                      'length': TOTAL_LENGTH,
                                      'host': host,
                                      'units': 'misc',
                                      'runner': 'netstat'}
