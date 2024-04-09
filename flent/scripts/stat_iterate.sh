#!/bin/bash

count=10
interval=0.1
host=localhost

while getopts "c:I:H:" opt; do
    case $opt in
        c) count=$OPTARG ;;
        I) interval=$OPTARG ;;
        H) host=$OPTARG ;;
    esac
done

# $5 is IDLE, $6 is IOWAIT; we count both as idle time
command_string=$(cat <<EOF
set -o noglob
awk -v COUNT=$count -v INTERVAL=$interval '
function get_cpu_usage(count) {
    FS = " ";
    IDLE_FIELD = 5;
    IOWAIT_FIELD = 6;
    PROC_CPU = "/proc/stat";
    while ((getline < PROC_CPU) > 0) {
        if (\$0 !~ /^cpu/)
            break;
        cpu_idle_prev[\$1] = cpu_idle[\$1];
        cpu_total_prev[\$1] = cpu_total[\$1];
        cpu_idle[\$1] = 0;
        cpu_total[\$1] = 0;
        for (i = 2; i <= NF; i++) {
            if (i == IDLE_FIELD || i == IOWAIT_FIELD)
                cpu_idle[\$1] += \$i;
            cpu_total[\$1] += \$i;
        }
        idle = cpu_idle[\$1] - cpu_idle_prev[\$1];
        total = cpu_total[\$1] - cpu_total_prev[\$1];
        cpu_usage = (total != 0) ? (1 - (idle / total)) : 0
        if (count)
            printf("%s: %f\n", \$1, cpu_usage);
    }
    close(PROC_CPU);
}

BEGIN {
    date_cmd = "date \"+Time: %s.%N\""
    for (loop = 0; loop < COUNT; loop++) {
        print("---");
	(date_cmd) | getline date;
        print(date);
        close(date_cmd);
        get_cpu_usage(loop);
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
