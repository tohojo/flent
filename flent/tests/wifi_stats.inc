## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add wifi stats to a test


WIFI_STATS_HOSTS=TEST_PARAMETERS.get('wifi_stats_hosts')
WIFI_STATS_IFACES=TEST_PARAMETERS.get('wifi_stats_interfaces')
WIFI_STATS_STATIONS=TEST_PARAMETERS.get('wifi_stats_stations')
if WIFI_STATS_HOSTS:
    for host,iface in zip(WIFI_STATS_HOSTS.split(","), WIFI_STATS_IFACES.split(",")):
        DATA_SETS['wifi_stats_%s' % host] = {'command': find_wifistats_iterate(iface, STEP_SIZE, TOTAL_LENGTH, host),
                                             'stations': WIFI_STATS_STATIONS.split(","),
                                             'units': 'misc',
                                             'runner': 'wifi_stats',}
        for station in WIFI_STATS_STATIONS.split(","):
            DATA_SETS['wifi_stats_%s::airtime_rx::%s' % (host,station)] = {'units': 'us', 'data_transform': 'cumulative_to_events',
                                                                           'runner': 'null', 'id': "%s::%s" % (host, station)}
            DATA_SETS['wifi_stats_%s::airtime_tx::%s' % (host,station)] = {'units': 'us', 'data_transform': 'cumulative_to_events',
                                                                           'runner': 'null', 'id': "%s::%s" % (host, station)}


    PLOTS['airtime_rx'] = {'description': 'WiFi RX airtime',
                           'type': 'timeseries',
                           'axis_labels': ['Microseconds'],
                           'series': [
                               {'data': glob('wifi_stats_*::airtime_rx*'),
                                'label': 'Airtime'},
                           ]}
    PLOTS['airtime_tx'] = {'description': 'WiFi TX airtime',
                           'type': 'timeseries',
                           'axis_labels': ['Microseconds'],
                           'series': [
                               {'data': glob('wifi_stats_*::airtime_tx*'),
                                'label': 'Airtime'},
                           ]}
