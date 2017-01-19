/* wifistats_iterate: Reliable, fast monitoring of some wifi stats
 * Author:   Dave Taht
 * Date:     13 Sept 2016
 * Copyright (C) 2016 Michael David Taht
 * Copyright (C) 2016 Toke Høiland-Jørgensen

 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#include <errno.h>
#include <locale.h>
#include <assert.h>
#include <getopt.h>
#include <iconv.h>
#include <fcntl.h>
#include <math.h>
#include <sys/types.h>
#include <dirent.h>
#include <sys/wait.h>
#include <sys/timerfd.h>
#include <sys/uio.h>

/*
  openwrt's ash shell does not have usleep,
  nor nanosecond time in the date command.
  find is expensive

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

  So this C program (which is more accurate and lighter weight
  than the shell script) needs to be used on things like lede,
  when high resolution data is needed. In fact, everywhere.
*/

#define BUFFERSIZE (1024*1024)
#define NSEC_PER_SEC (1000000000.0)

typedef struct {
	int rc_stats;
	int airtime;
	char macaddr[6*3];
	char airtime_file[256];
	char rc_stats_file[256];
} station_stats;

struct arg {
	int count;
	struct timespec interval;
	double finterval;
	char *filename;
	char *dev;
	station_stats *stations;
	char buffer;
};

typedef struct arg args;

static const struct option long_options[] = {
	{ "count"    , required_argument	, NULL , 'c' } ,
	{ "interval" , required_argument	, NULL , 'I' } ,
	{ "interface", required_argument	, NULL , 'i' } ,
	{ "help"     , no_argument		, NULL , 'h' } ,
	{ "buffer"   , no_argument		, NULL , 'b' } ,
};

void usage (char *err) {
	if(err) fprintf(stderr,"%s\n",err);
	printf("wifistats_iterate [options]\n");
	printf(
		"\t-h --help \n"
		"\t-b --buffer    [buffer up the output locally]\n"
		"\t-c --count     [number of iterations]\n"
		"\t-I --interval  [fractional number of seconds]\n"
		"\t-i --interface [wifi interface]\n"
		);
	exit(-1);
}

// The way I originally did this was to open the fd and lseek to the beginning
// That doesn't work with rc_stats, so we need to open the file every time. Sigh.
// Or I had a bug elsewhere. ?
// If a station goes away, it's handled in stations_read

int stations_reset(station_stats *stations, int cnt) {
	for(int i = 0; i < cnt; i++) {
		if (stations[i].rc_stats)
			close(stations[i].rc_stats);
		if (stations[i].airtime)
			close(stations[i].airtime);
		stations[i].rc_stats = open(stations[i].rc_stats_file,O_RDONLY);
		stations[i].airtime = open(stations[i].airtime_file,O_RDONLY);
	}
	return 0;
}

int stations_bsize(station_stats *stations, int pad) {
	int size = 0;
	int j = 0;
	for(int i = 0; stations[i].rc_stats > 0; i++) {
		if((j = lseek(stations[i].rc_stats,0,SEEK_END)) > 0) size+=j+pad;
		if((j = lseek(stations[i].airtime, 0,SEEK_END)) > 0) size+=j+pad;
	}
	return size;
}

// NOTE: You must closedir the resulting pointer

DIR *dir_exists(char * dir) {
	DIR* fd;
	struct dirent* in;

	if (NULL == (fd = opendir (dir)))
	{
		perror("Error : Failed to open stations directory");
		return NULL;
	}
	return fd;
}

#define MAXPATHLEN 1024

int wifi_where(char * dev) {
	char  buf[1024];
	DIR *fd;
	for(int i = 0; i < 10; i++) {
		sprintf(buf,"/sys/kernel/debug/ieee80211/phy%i/netdev:%s/stations",i,dev);
		if((fd = dir_exists(buf)) != NULL) {
			closedir(fd);
			return i;
		}
	}
	return -1;
}

int count_stations(char * dev) {
	int cnt = 0;
	DIR* fd;
	struct dirent* in;
	char dir[1024];
	sprintf(dir,"/sys/kernel/debug/ieee80211/phy%i/netdev:%s/stations",
		wifi_where(dev),dev);

	if ((fd = dir_exists(dir)) == NULL) return -1;

	while ((in = readdir(fd)))
	{
		if (!strcmp (in->d_name, "."))
			continue;
		if (!strcmp (in->d_name, ".."))
			continue;
		cnt++;
	}
	closedir(fd);
	return cnt;
}

int stations_open(char * dev, station_stats *stations, int limit) {
	int cnt = 0;
	DIR* fd;
	int f;
	struct dirent* in;
	char dir[MAXPATHLEN];
	char airtime[MAXPATHLEN];
	char rc_stats[MAXPATHLEN];

	stations[cnt].rc_stats = stations[cnt].airtime = -1;
	limit /= 2;
	sprintf(dir,"/sys/kernel/debug/ieee80211/phy%i/netdev:%s/stations",
		wifi_where(dev),dev);

	if ((fd = dir_exists(dir)) == NULL) return -1;

	while ((in = readdir(fd)))
	{
		if (!strcmp (in->d_name, "."))
			continue;
		if (!strcmp (in->d_name, ".."))
			continue;

		sprintf(stations[cnt].macaddr,"%s",in->d_name);
		sprintf(stations[cnt].rc_stats_file,"%s/%s/%s",dir,in->d_name,"rc_stats_csv");
		sprintf(stations[cnt].airtime_file,"%s/%s/%s",dir,in->d_name,"airtime");

		if(++cnt > limit) {
			perror("Error : Too many stations to process\n");
			break;
		}
	}
	stations[cnt].rc_stats = stations[cnt].airtime = -1;
	closedir(fd);
	return cnt;
}

int stations_close(station_stats *stations, int cnt) {
	for (int i = 0; i < cnt ; i++) {
		close(stations[i].rc_stats);
		close(stations[i].airtime);
	}
	return(0);
}

int stations_read(station_stats *s, char * buf, int cnt) {
	int i = 0;
	int size = 0;

	while(i < cnt) {
		int t = 0;
		size += sprintf(&buf[size],"Station: %s\n",s[i].macaddr);
		if(s[i].airtime > 0) {
			size += sprintf(&buf[size],"Airtime:\n");
			if((t = read(s[i].airtime, &buf[size],8192)) > 0) size += t;
		}
		if(s[i].rc_stats > 0) {
			size += sprintf(&buf[size],"RC stats:\n");
			if((t = read(s[i].rc_stats,&buf[size],8192)) > 0) size += t;
		}
		i++;
	}

	return size;
}

static void defaults(args *a) {
	a->filename = NULL;
	a->dev = NULL;
	a->stations = NULL;
	a->finterval=.2;
	a->count=10;
	a->interval.tv_nsec = 0;
	a->interval.tv_sec = 0;
	a->buffer = 0;
}

#define QSTRING "c:I:f:i:hb"

int process_options(int argc, char **argv, args *o)
{
	int          option_index = 0;
	int          opt = 0;
	optind       = 1;

	while(1)
	{
		opt = getopt_long(argc, argv,
				  QSTRING,
				  long_options, &option_index);
		if(opt == -1) break;

		switch (opt)
		{
		case 'c': o->count = strtoul(optarg,NULL,10);  break;
		case 'I': o->finterval = strtod(optarg,NULL); break;
		case 'f': o->filename = optarg; break;
		case 'i': o->dev = optarg; break;
		case 'b': o->buffer = 1; break;
		case '?':
		case 'h': usage(NULL); break;
		default:  usage(NULL);
		}
	}
	o->interval.tv_sec = floor(o->finterval);
	o->interval.tv_nsec = (long long) ((o->finterval - o->interval.tv_sec) * NSEC_PER_SEC);
	return 0;
}

static int result(int out, int size, int bufsize, char *buffer) {
	struct timespec cur_time;
	struct iovec iov[3];
	int err = 0;
	char mtime[40];
	int added = 0;
	clock_gettime(CLOCK_REALTIME, &cur_time);
	added = sprintf(mtime,"Time: %ld.%09ld\n",
			    cur_time.tv_sec,cur_time.tv_nsec);

	iov[0].iov_base = mtime;
	iov[0].iov_len = added;

	iov[1].iov_base = buffer;
	iov[1].iov_len = size;

	iov[2].iov_base = "---\n";
	iov[2].iov_len = sizeof("---\n")-1;

	if(bufsize - size > 40) {
  		if(( err = writev(out,iov,3) == -1)) {
			perror("Write failed - out of disk?");
		}
	} else {
		write(2,"Buffer Overrun\n",sizeof("Buffer Overrun\n"));
	}
	return err;
}

// Since this is linux only we can use timerfd for an isochronous clock

#define STABUF 8192 // hopefully big enough? (802.11ac?)

int run(args *a)
{
	char tmpfile[] = "/tmp/wifistats_iterateXXXXXX";
	int out = a->buffer ? mkstemp(tmpfile) : STDOUT_FILENO;
	station_stats *stations = NULL;
	char *buf;
	int c;

	if(a->buffer && !out) {
		perror("Unable to create tmpfile");
		exit(-1);
	} else {
		unlink(tmpfile); // make it disappear on close
	}

//	if (!a->filename)
//		usage("Must specify filename");

	if (!a->dev)
		usage("Must specify wifi device");

	if((c = count_stations(a->dev)) > 0) {
		if((a->stations = malloc(2*c*sizeof(station_stats))) == NULL)
		{
			perror("Unable to allocate memory");
			exit(-1);
		}
		if((buf = malloc(2*c*STABUF)) == NULL)
		{
			perror("Unable to allocate memory");
			exit(-1);
		}
	} else {
		usage("No stations found");
	}

	if((c = stations_open(a->dev,a->stations,512)) < 1) usage("No stations found");

	struct itimerspec new_value = {0};

	int timer = timerfd_create(CLOCK_REALTIME, 0);
	new_value.it_interval = a->interval;
	new_value.it_value = a->interval;

	/* better method would be to poll for input (since writes from the
	   tool could block or return no output for some reason), timestamp the input,
	   and if the difference is less than half, skip this round.
	   this would absorb non-completing stuff */

	char buffer[BUFFERSIZE];
	int size = 0;
	int ctr = 0;
	stations = a->stations;

	timerfd_settime(timer,0,&new_value,NULL); // relative timer

	do {
		int err;
		long long fired;
		if(read(timer,&fired,sizeof(fired))!=8) perror("reading timer");
		ctr+=fired;

		stations_reset(stations,c);
		if((size = stations_read(stations,buffer,c)) > 0) {
			err = result(out,size,BUFFERSIZE,buffer);
		} else {
			err = result(out,0,BUFFERSIZE,buffer);
			perror("reading file");
		}
		if(err<0) break;
	} while (ctr < a->count);

	if(a->buffer) {
		lseek(out, 0, SEEK_SET);
		while((size = read(out, buffer, sizeof(buffer))) > 0)
			write(STDOUT_FILENO,buffer,size);
	}

	close(out);
	close(timer);
	stations_close(stations,c);
	free(buf);
	free(stations);
	a->stations = NULL;
	return 0;
}

int main(int argc,char **argv) {
	args a;
	int status = 0;
	defaults(&a);
	process_options(argc, argv, &a);
	run(&a);
	return status;
}
