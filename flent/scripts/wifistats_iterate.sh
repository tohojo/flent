#!/bin/bash

count=10
interval=0.1
host=localhost

while getopts "i:c:I:H:" opt; do
    case $opt in
        i) interface=$OPTARG ;;
        c) count=$OPTARG ;;
        I) interval=$OPTARG ;;
        H) host=$OPTARG ;;
    esac
done

command_string=$(cat <<EOF
which wifistats_iterate >/dev/null && exec wifistats_iterate $buffer -i $interface -c $count -I $interval;
for i in \$(seq $count); do
    date '+Time: %s.%N';
    dir=\$(find /sys/kernel/debug/ieee80211 -name netdev:$interface);
    for s in \$dir/stations/*; do
        echo Station: \$(basename \$s);
        [ -f \$s/airtime ] && echo Airtime: && cat \$s/airtime;
        [ -f \$s/rc_stats_csv ] && echo RC stats: && cat \$s/rc_stats_csv;
    done;
    echo "---";
    sleep $interval || exit 1;
done
EOF
)

if [ "$host" == "localhost" ]; then
    eval $command_string
else
    echo $command_string | ssh $host sh
fi
