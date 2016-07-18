## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add extra hosts to ping


PING_HOSTS=TEST_PARAMETERS.get('ping_hosts')
PING_LOCAL_BINDS=TEST_PARAMETERS.get('ping_local_binds')
if PING_LOCAL_BINDS:
    PING_LOCAL_BINDS = PING_LOCAL_BINDS.split(",")
if PING_HOSTS:
    for i,host in enumerate(PING_HOSTS.split(",")):
        local_bind = PING_LOCAL_BINDS[i] if PING_LOCAL_BINDS else None
        DATA_SETS['Ping (ms) ICMP %s (extra)' % host] = {'command': find_ping(IP_VERSION, STEP_SIZE, TOTAL_LENGTH, host, local_bind=local_bind),
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
    PLOTS['ping_extra_combine'] = {'description': 'Extra ping hosts (combine)',
                                   'type': 'cdf_combine',
                                   'group_by': 'groups_concat',
                                   'cutoff': (DELAY,DELAY),
                                   'axis_labels': ['Latency (ms)'],
                                   'series': [
                                       {'data': glob('Ping (ms) ICMP * (extra)'),
                                        'label': 'Ping (ms)'},
                                   ]}
