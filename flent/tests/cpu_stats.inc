## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add cpu stats to a test


CPU_STATS_HOSTS=TEST_PARAMETERS.get('cpu_stats_hosts')
if CPU_STATS_HOSTS:
    for host in CPU_STATS_HOSTS.split(","):
        DATA_SETS['cpu_stats_%s' % host] = {'command': find_stat_iterate(STEP_SIZE, TOTAL_LENGTH, host),
                                              'units': 'misc',
                                              'runner': 'cpu_stats',}
        DATA_SETS['cpu_stats_%s::load' % host] = {'units': 'fraction', 'runner': 'null', 'id': host}

    PLOTS['cpu'] = {'description': 'CPU stats',
                    'type': 'timeseries',
                    'axis_labels': ['Load'],
                    'series': [
                        {'data': glob('cpu_stats_*::load'),
                         'label': 'CPU load'},
                    ]}
