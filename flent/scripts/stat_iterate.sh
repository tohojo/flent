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
(for x in \$(seq $count); do date '+Time: %s.%N'; cat /proc/stat; sleep $interval ;done ) | awk 'BEGIN {idle=0; total=0}
\$1 == "cpu" { sum=0; for (i=2;i<=NF;i++) { sum+=\$i };
              if(total>0) {print \$5+\$6-idle " " sum-total " " 1-(\$5+\$6-idle)/(sum-total);}
              idle=\$5+\$6; total=sum
            }
\$1 == "Time:" { print "---\n" \$0 }'
EOF
)

if [ "$host" == "localhost" ]; then
    eval $command_string
else
    echo $command_string | ssh $host sh
fi
