#!/bin/bash
# SPDX-License-Identifier: GPL-3.0
# SPDX-FileContributor: Freysteinn Alfredsson <freysteinn@freysteinn.com>
# SPDX-FileType: SOURCE

count=10
interval=0.1
host=localhost
exact_values=0

while getopts "c:I:H:d:f:e" opt; do
    case $opt in
        c) count=$OPTARG ;;
        I) interval=$OPTARG ;;
        H) host=$OPTARG ;;
        d) devices=$OPTARG ;;
        f) fields=$OPTARG ;;
        e) exact_values=1 ;;
    esac
done

command_string=$(cat <<EOF
awk -v COUNT="$count" \
    -v INTERVAL="$interval" \
    -v DEVICES="$devices" \
    -v FIELDS="$fields" \
    -v EXACT_VALUES="$exact_values" ' \
function add_device(device)
{
    ethtool_cmd = ETHTOOL_CMD_TEMPLATE " " device;
    for (device_id in devices)
        if (device == devices[device_id])
            return;

    if (((ethtool_cmd) | getline) > 0)
        devices[device_id_count++] = device;
    close(ethtool_cmd);
}

function add_field(device, field)
{
    if (entries[device, field] != 1)
        device_entry_count[device]++;
    entries[device, field] = 1;

    for (field_id in fields)
        if (field == fields[field_id])
            return;
    fields[field_id_count++] = field;
}

# Startup
BEGIN {
    ETHTOOL_CMD_TEMPLATE = "ethtool -S "
    DEVICE_LIST_CMD = "ls /sys/class/net";
    device_id_count = 0;
    field_id_count = 0;

    # Set default fields if not specified
    if (FIELDS == "") {
        FIELDS = "rx_packets,tx_packets";
    }

    split(DEVICES, device_args, ",");
    split(FIELDS, field_params, ",");

    # Get devices
    while (((DEVICE_LIST_CMD) | getline) > 0) {
        if (\$1 == "lo")
            continue;
        # Only add devices specified in DEVICES
        if (DEVICES != "") {
            for (device_arg_id in device_args) {
                if (\$1 == device_args[device_arg_id])
                    add_device(\$1);
            }
        } else {
            # Add all devices if DEVICES is not specified
            add_device(\$1);
        }
    }
    close(DEVICE_LIST_CMD);

    # Get fields
    for (field_param_id in field_params) {
        field_count = 0;
        split(field_params[field_param_id], field_pair, ":");
        for (pair_id in field_pair)
            field_count++;
        field = field_pair[field_count];

        # Add device specific fields
        if (field_count == 2) {
            device = field_pair[1];
            add_device(device);
            add_field(device, field);
            continue
        }

        # Add global fields to all devices
        for (device_id in devices) {
            device = devices[device_id];
            add_field(device, field);
        }
    }
}

function update_ethtool_stat(device)
{
    FS = ":";
    ethtool_cmd = ETHTOOL_CMD_TEMPLATE " " device;
    found_fields = 0;

    while (((ethtool_cmd) | getline) > 0) {
        for (field_id in fields) {
            field = fields[field_id];
            field_regexp = "^ *" field "\$";
            if (\$1 !~ field_regexp)
                continue;
            value = \$2;

            entry_value_prev[device, field] = entry_value[device, field];
            entry_value[device, field] = value;

            found_fields++;
            if (found_fields == device_entry_count[device])
                break;
        }
    }
    close(ethtool_cmd);
}

function print_values(device)
{
    for (field_id in fields) {
        field = fields[field_id];
        if (entries[device, field] != 1)
            continue;

        value_prev = entry_value_prev[device, field];
        value = entry_value[device, field];

        result = value - value_prev;
        result = EXACT_VALUES == 1 ? result : result / INTERVAL;

        print(device ":" field ": " result);
    }
}

# Main loop
BEGIN {
    DATE_CMD = "date \"+Time: %s.%N\""

    # Update initial values
    for (device_id in devices) {
        device = devices[device_id];
        update_ethtool_stat(device);
    }

    # Print interval values
    for (i = 0; i < COUNT; i++) {
        print("---");
        (DATE_CMD) | getline date;
        print(date);
        close(DATE_CMD);

        for (device_id in devices) {
            device = devices[device_id];
            update_ethtool_stat(device);
            print_values(device);
        }
        system("sleep " INTERVAL);
    }
}'
EOF
)

if [ "$host" == "localhost" ]; then
    eval "$command_string"
else
    echo "$command_string" | ssh "$host" sh
fi
