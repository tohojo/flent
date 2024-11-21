#!/bin/bash

length=20
interval=0.1
command="echo 1"
host=localhost

while getopts "l:I:C:H:" opt; do
    case $opt in
        l) length=$OPTARG ;;
        I) interval=$OPTARG ;;
        C) command=$OPTARG ;;
        H) host=$OPTARG ;;
    esac
done

command_string=$(cat <<EOF
endtime=\$(date -d "$length sec" +%s%N);
while [ "\$(date +%s%N)" -le "\$endtime" ]; do
    $command;
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
