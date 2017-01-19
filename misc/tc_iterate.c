/* tc_iterate: Reliable, fast monitoring of tc
 * Author:   Dave Taht
 * Date:     22 Nov 2015
 * Copyright (C) 2015 Michael David Taht
 * Copyright (C) 2015 Toke Høiland-Jørgensen

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
#include <sys/wait.h>
#include <sys/timerfd.h>

/*
  openwrt's ash shell does not have usleep,
  nor nanosecond time in the date command.

  for i in $(seq $count); do
  tc -s $command show dev $interface
  date '+Time: %s.%N'
  echo "---"
  sleep $interval
  done

  So this C program (which is more accurate and lighter weight
  than the shell script) needs to be used on things like openwrt,
  or when high resolution tc statistics are desired.
*/

#define BUFFERSIZE (1024*1024)
#define NSEC_PER_SEC (1000000000.0)

struct arg {
	int count;
	struct timespec interval;
	double finterval;
	char *interface;
	char *command;
	char buffer;
};

typedef struct arg args;

static const struct option long_options[] = {
	{ "interface", required_argument	, NULL , 'i' } ,
	{ "count"    , required_argument	, NULL , 'c' } ,
	{ "interval" , required_argument	, NULL , 'I' } ,
	{ "command"  , required_argument	, NULL , 'C' } ,
	{ "help"     , no_argument		, NULL , 'h' } ,
	{ "buffer"   , no_argument		, NULL , 'b' } ,
};

void usage (char *err) {
	if(err) fprintf(stderr,"%s\n",err);
	printf("tc_iterate [options]\n");
	printf(
		"\t-h --help \n"
		"\t-b --buffer \n"
		"\t-i --interface [eth0*,wlan0,etc]\n"
		"\t-c --count     [number of iterations]\n"
		"\t-I --interval  [fractional number of seconds]\n"
		"\t-C --command   [qdisc]\n");
	exit(-1);
}

static void defaults(args *a) {
	a->interface = "eth0";
	a->command = "qdisc";
	a->finterval=.2;
	a->count=10;
	a->interval.tv_nsec = 0;
	a->interval.tv_sec = 0;
	a->buffer = 0;
}

#define QSTRING "i:c:I:C:hb"

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
		case 'C': o->command = optarg; break;
		case 'i': o->interface = optarg; break;
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


static void result(int out, int size, int bufsize, char *buffer) {
	struct timespec cur_time;
	if(bufsize - size > 40) {
		clock_gettime(CLOCK_REALTIME, &cur_time);
		int added = sprintf(&buffer[size],"Time: %ld.%09ld\n---\n",
				    cur_time.tv_sec,cur_time.tv_nsec);
  		write(out,buffer,size+added);
	} else {
		write(2,"Buffer Overrun\n",sizeof("Buffer Overrun\n"));
	}
}

// Since this is linux only we can use timerfd for an isochronous clock

int forkit(args *a)
{
	int filedes[2]; // 0 = read
	int filedes2[2]; // 0 = read
	pipe(filedes);
	pipe(filedes2);
	int tool = filedes[1]; // write this
	int in = filedes2[0]; // connect out to in
	char tmpfile[] = "/tmp/tc_iterateXXXXXX";
	int out = a->buffer ? mkstemp(tmpfile) : STDOUT_FILENO;
	pid_t child;

	if(a->buffer && !out) {
		perror("Unable to create tmpfile");
		exit(-1);
	}
	// probably want the pipe line buffered via fcntl
	if((child = fork())==0)
	{
		close(filedes[1]);
		close(filedes2[0]);
		dup2(filedes2[1],STDOUT_FILENO);
		dup2(filedes[0],STDIN_FILENO);

		if(execlp("tc", "tc", "-s", "-b", "-",NULL)==-1) {
			perror("Failed to execute cmd");
			exit(-1);
		}
	}
	close(filedes2[1]);
	close(filedes[0]);
	struct itimerspec new_value = {0};

	int timer = timerfd_create(CLOCK_REALTIME, 0);


	new_value.it_interval = a->interval;
	new_value.it_value = a->interval;

	/* better method would be to poll for input (since writes from the
	   tool could block or return no output for some reason), timestamp the input,
	   and if the difference is less than half, skip this round.
	   this would absorb non-completing stuff */

	char buffer[BUFFERSIZE];
	char cmd[1024];
	int size = 0;
	sprintf(cmd,"%s show dev %s\n",a->command,a->interface);
	int csize = strlen(cmd);
	int ctr = 0;
	timerfd_settime(timer,0,&new_value,NULL); // relative timer

	do {
		long long fired;
		if(write(tool,cmd,csize)==-1) perror("writing cmd");
		if(read(timer,&fired,sizeof(fired))!=8) perror("reading timer");
		ctr+=fired;
		if((size = read(in,buffer,sizeof(buffer))) > 0) {
			result(out,size,BUFFERSIZE,buffer);
		} else {
			result(out,0,BUFFERSIZE,buffer);
			perror("reading cmd output");
		}
	} while (ctr < a->count);
	close(tool);
	close(in);
	if(a->buffer) {
		lseek(out, 0, SEEK_SET);
		while((size = read(out, buffer, sizeof(buffer))) > 0)
			write(STDOUT_FILENO,buffer,size);
		unlink(tmpfile);
	}
	close(out);
	wait(NULL);
	return 0;
}

int main(int argc,char **argv) {
	args a;
	int status = 0;
	defaults(&a);
	process_options(argc, argv, &a);
	forkit(&a);
	return status;
}
