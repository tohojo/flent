STRIP:=strip
PREFIX:=/usr/local
DESTDIR:=$(PREFIX)/bin
PROGS:= tc_iterate wifistats_iterate

all: $(PROGS)

tc_iterate: tc_iterate.c
	$(CC) tc_iterate.c -o tc_iterate -lm -lrt

wifistats_iterate: wifistats_iterate.c
	$(CC) wifistats_iterate.c -o wifistats_iterate -lm -lrt

file_iterate: file_iterate.c
	$(CC) file_iterate.c -o file_iterate -lm -lrt

install: tc_iterate
	$(STRIP) $(PROGS)
	install -d -m0755 $(DESTDIR)
	install -m0755 $(PROGS) $(DESTDIR)

clean:
	rm -f *.o $(PROGS)
