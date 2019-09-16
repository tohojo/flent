## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add extra hosts to ping


PING_HOSTS=get_test_parameter('ping_hosts', default=[], split=True)
PING_LOCAL_BINDS=get_test_parameter('ping_local_binds', default=[], split=True)
PING_MARKINGS=get_test_parameter('ping_markings', default=[], split=True)

for host, local_bind, marking in zip_longest(PING_HOSTS, PING_LOCAL_BINDS,
                                             PING_MARKINGS):
    if not host:
        break
    DATA_SETS['Ping (ms) ICMP %s (extra)' % host] = {'ip_version': IP_VERSION,
                                                     'interval': STEP_SIZE,
                                                     'length': TOTAL_LENGTH,
                                                     'host': host,
                                                     'local_bind': local_bind,
                                                     'marking': marking,
                                                     'units': 'ms',
                                                     'id': '%s ICMP' % host,
                                                     'runner': 'ping'}

if PING_HOSTS:

    PLOTS['ping_extra'] = {'description': 'Extra ping hosts',
                    'type': 'timeseries',
                    'axis_labels': ['Latency (ms)'],
                    'series': [
                        {'data': glob('Ping (ms) ICMP * (extra)'),
                         'label': 'Ping (ms)'},
                    ]}
    PLOTS['ping_extra_combine'] = {'description': 'Extra ping hosts (combine)',
                                   'type': 'cdf_combine',
                                   'group_by': 'groups_concat',
                                   'cutoff': (DELAY,-DELAY),
                                   'axis_labels': ['Latency (ms)'],
                                   'series': [
                                       {'data': glob('Ping (ms) ICMP * (extra)'),
                                        'label': 'Ping (ms)'},
                                   ]}
