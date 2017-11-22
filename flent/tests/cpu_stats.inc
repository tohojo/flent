## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add cpu stats to a test


CPU_STATS_HOSTS=TEST_PARAMETERS.get('cpu_stats_hosts')
if CPU_STATS_HOSTS:
    for host in CPU_STATS_HOSTS.split(","):
        DATA_SETS['cpu_stats_%s' % host] = {'interval': STEP_SIZE, 'length': TOTAL_LENGTH, 'host': host, 'units':
                                            'misc', 'id': host, 'runner': 'cpu_stats'}

    PLOTS['cpu'] = {'description': 'CPU stats',
                    'type': 'timeseries',
                    'axis_labels': ['Load'],
                    'series': [
                        {'data': glob('cpu_stats_*'),
                         'raw_key': 'load',
                         'label': 'CPU load'},
                    ]}

    PLOTS['cpu_box'] = {'description': 'CPU stats (box plot)',
                        'type': 'box',
                        'parent': 'cpu'}
    PLOTS['cpu_bar'] = {'description': 'CPU stats (bar plot)',
                        'type': 'bar',
                        'parent': 'cpu'}

    PLOTS['cpu_box_combine'] = {'description': 'CPU stats (box combine plot)',
                                'type': 'box_combine',
                                'axis_labels': ['Load'],
                                'series': [
                                    {'data': glob('cpu_stats_*'),
                                     'raw_key': 'load',
                                     'label': 'CPU load',
                                     'combine_mode': 'raw_mean'},
                                ]}
    PLOTS['cpu_bar_combine'] = {'description': 'CPU stats (bar combine plot)',
                                'type': 'bar_combine',
                                'parent': 'cpu_box_combine'}
