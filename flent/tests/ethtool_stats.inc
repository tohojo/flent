## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add cpu stats to a test


ETHTOOL_HOSTS=get_test_parameter('ethtool_hosts', default=[], split=True)
ETHTOOL_DEVICES=get_test_parameter('ethtool_devices', default=None)
ETHTOOL_FIELDS=get_test_parameter('ethtool_fields', default=None)

for host in ETHTOOL_HOSTS:
    DATA_SETS['ethtool_stats_%s' % host] = {'interval': STEP_SIZE,
                                        'length': TOTAL_LENGTH,
                                        'host': host,
                                        'units': 'misc',
                                        'id': host,
                                        'devices': ETHTOOL_DEVICES,
                                        'fields': ETHTOOL_FIELDS,
                                        'runner': 'ethtool_stats'}

if ETHTOOL_HOSTS:
    PLOTS['ethtool'] = {'description': 'Per ethtool field stats',
                    'type': 'timeseries',
                    'axis_labels': ['value'],
                    'series': [
                        {'data': glob('ethtool_stats_*'),
                         'raw_key': glob('*', exclude=["t"]),
                         'label': 'Ethtool field stats'},
                    ]}

    PLOTS['ethtool_box'] = {'description': 'Per ethtool stats (box plot)',
                        'type': 'box',
                        'parent': 'ethtool'}

    PLOTS['ethtool_bar'] = {'description': 'Per ethtool stats (bar plot)',
                        'type': 'bar',
                        'parent': 'ethtool'}
