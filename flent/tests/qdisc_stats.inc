## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add qdisc stats to a test


QDISC_STATS_HOSTS=TEST_PARAMETERS.get('qdisc_stats_hosts')
QDISC_STATS_IFACES=TEST_PARAMETERS.get('qdisc_stats_interfaces')
if QDISC_STATS_HOSTS:
    for host,iface in zip(QDISC_STATS_HOSTS.split(","), QDISC_STATS_IFACES.split(",")):
        id = "%s (%s)" % (host, iface)
        DATA_SETS['qdisc_stats_%s' % host] = {'interface': iface, 'interval': STEP_SIZE, 'length': TOTAL_LENGTH, 'host':
                                              host, 'id': id, 'units': 'misc', 'runner': 'tc'}
        DATA_SETS['qdisc_stats_%s::dropped' % host] = {'units': 'packets', 'data_transform': 'cumulative_to_events', 'runner': 'null', 'id': id}
        DATA_SETS['qdisc_stats_%s::ecn_mark' % host] = {'units': 'packets', 'data_transform': 'cumulative_to_events', 'runner': 'null', 'id': id}

    PLOTS['backlog'] = {'description': 'Queue backlog',
                        'type': 'timeseries',
                        'axis_labels': ['Bytes'],
                        'series': [
                            {'data': glob('qdisc_stats_*'),
                             'raw_key': 'backlog_bytes',
                             'label': 'Backlog (bytes)'},
                        ]}

    PLOTS['drops'] = {'description': 'Packet drops',
                      'type': 'timeseries',
                      'axis_labels': ['Packets'],
                      'series': [
                          {'data': glob('qdisc_stats_*'),
                           'label': 'Drops',
                           'raw_key': 'dropped',
                           'linestyle': '',
                           'marker': 'x'},
                          {'data': glob('qdisc_stats_*'),
                           'label': 'ECN marks',
                           'raw_key': 'ecn_mark',
                           'linestyle': '',
                           'marker': 'o'}
                      ]}

    PLOTS['delay'] = {'description': 'Queue delay',
                      'type': 'timeseries',
                      'axis_labels': ['Queueing delay (ms)'],
                      'series': [
                          {'data': glob('qdisc_stats_*'),
                           'raw_key': 'delay',
                           'label': 'Queue delay'}
                      ]}
