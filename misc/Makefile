STRIP:=strip
PREFIX:=/usr/local
DESTDIR:=$(PREFIX)/bin

all: tc_iterate

tc_iterate: tc_iterate.c
	$(CC) tc_iterate.c -o tc_iterate -lm -lrt

install: tc_iterate
	$(STRIP) tc_iterate
	install -d -m0755 $(DESTDIR)
	install -m0755 tc_iterate $(DESTDIR)

clean:
	rm -f *.o tc_iterate
