#!/bin/bash

interface=eth0
count=10
interval=0.1
command=qdisc
host=localhost

while getopts "i:c:I:C:H:" opt; do
    case $opt in
        i) interface=$OPTARG ;;
        c) count=$OPTARG ;;
        I) interval=$OPTARG ;;
        C) command=$OPTARG ;;
        H) host=$OPTARG ;;
    esac
done

buffer=""
[[ "$host" == "localhost" ]] || buffer="-b"


command_string=$(cat <<EOF
which tc_iterate >/dev/null && exec tc_iterate $buffer -i $interface -c $count -I $interval -C $command;
for i in \$(seq $count); do
    tc -s $command show dev $interface;
    date '+Time: %s.%N';
    echo "---";
    sleep $interval || exit 1;
done
EOF
)

if [[ "$host" == "localhost" ]]; then
    eval $command_string
else
    echo $command_string | ssh $host sh
fi
