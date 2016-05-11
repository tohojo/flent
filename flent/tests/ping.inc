## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add extra hosts to ping


PING_HOSTS=TEST_PARAMETERS.get('ping_hosts')
if PING_HOSTS:
    for host in PING_HOSTS.split(","):
        DATA_SETS['Ping (ms) ICMP %s (extra)' % host] = {'command': find_ping(IP_VERSION, STEP_SIZE, TOTAL_LENGTH, host),
                                                         'units': 'ms',
                                                         'id': host,
                                                         'runner': 'ping',}

    PLOTS['ping_extra'] = {'description': 'Extra ping hosts',
                    'type': 'timeseries',
                    'axis_labels': ['Latency (ms)'],
                    'series': [
                        {'data': glob('Ping (ms) ICMP * (extra)'),
                         'label': 'Ping (ms)'},
                    ]}
