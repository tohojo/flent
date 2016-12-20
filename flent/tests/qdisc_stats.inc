## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add qdisc stats to a test


QDISC_STATS_HOSTS=TEST_PARAMETERS.get('qdisc_stats_hosts')
QDISC_STATS_IFACES=TEST_PARAMETERS.get('qdisc_stats_interfaces')
if QDISC_STATS_HOSTS:
    for host,iface in zip(QDISC_STATS_HOSTS.split(","), QDISC_STATS_IFACES.split(",")):
        DATA_SETS['qdisc_stats_%s' % host] = {'command': find_tc_iterate(iface, STEP_SIZE, TOTAL_LENGTH, host),
                                              'units': 'misc',
                                              'runner': 'tc',}
        DATA_SETS['qdisc_stats_%s::backlog_pkts' % host] = {'units': 'packets', 'runner': 'null', 'id': host}
        DATA_SETS['qdisc_stats_%s::sent_pkts' % host] = {'units': 'packets', 'runner': 'null', 'id': host}
        DATA_SETS['qdisc_stats_%s::backlog_bytes' % host] = {'units': 'bytes', 'runner': 'null', 'id': host}
        DATA_SETS['qdisc_stats_%s::sent_bytes' % host] = {'units': 'bytes', 'runner': 'null', 'id': host}
        DATA_SETS['qdisc_stats_%s::backlog_requeues' % host] = {'units': 'packets', 'runner': 'null', 'id': host}
        DATA_SETS['qdisc_stats_%s::requeues' % host] = {'units': 'packets', 'runner': 'null', 'id': host}
        DATA_SETS['qdisc_stats_%s::overlimits' % host] = {'units': 'packets', 'runner': 'null', 'id': host}
        DATA_SETS['qdisc_stats_%s::dropped' % host] = {'units': 'packets', 'data_transform': 'cumulative_to_events', 'runner': 'null', 'id': host}
        DATA_SETS['qdisc_stats_%s::ecn_mark' % host] = {'units': 'packets', 'data_transform': 'cumulative_to_events', 'runner': 'null', 'id': host}
        DATA_SETS['qdisc_stats_%s::delay' % host] = {'units': 'ms', 'runner': 'null'}

    PLOTS['backlog'] = {'description': 'Queue backlog',
                        'type': 'timeseries',
                        'axis_labels': ['Packets', 'Bytes'],
                        'dual_axes': True,
                        'series': [
                            {'data': glob('qdisc_stats_*::backlog_pkts'),
                             'label': 'Backlog (packets)'},
                            {'data': glob('qdisc_stats_*::backlog_bytes'),
                             'label': 'Backlog (bytes)',
                             'axis': 2},
                        ]}

    PLOTS['drops'] = {'description': 'Packet drops',
                      'type': 'timeseries',
                      'axis_labels': ['Packets'],
                      'series': [
                          {'data': glob('qdisc_stats_*::dropped'),
                           'label': 'Drops',
                           'linestyle': '',
                           'marker': 'x'},
                          {'data': glob('qdisc_stats_*::ecn_mark'),
                           'label': 'ECN marks',
                           'linestyle': '',
                           'marker': 'o'}
                      ]}

    PLOTS['delay'] = {'description': 'Queue delay',
                      'type': 'timeseries',
                      'axis_labels': ['Queueing delay (ms)'],
                      'series': [
                          {'data': glob('qdisc_stats_*::delay'),
                           'label': 'Queue delay'}
                      ]}
