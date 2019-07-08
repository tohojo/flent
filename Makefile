PYTHON:=python
PREFIX:=/usr

all: build

build: flent/*.py
	$(PYTHON) setup.py build

.PHONY: test
test:
	$(PYTHON) setup.py test -r unittests:TestRunner

.PHONY: test_long
test_long:
	$(PYTHON) setup.py test -s unittests.all_tests -r unittests:TestRunner


.PHONY: install
install:
	$(PYTHON) setup.py install
	install -m 0755 -D -d $(PREFIX)/share/doc/flent/misc
	install -m 0644 -D -t $(PREFIX)/share/doc/flent BUGS README.rst *.example
	install -m 0644 -D -t $(PREFIX)/share/doc/flent/misc misc/*
	install -m 0644 -t $(PREFIX)/share/man/man1 man/flent.1
	install -m 0644 -t $(PREFIX)/share/mime/packages flent-mime.xml
	install -m 0644 -t $(PREFIX)/share/applications flent.desktop
	install -m 0644 -t $(PREFIX)/share/metainfo flent.appdata.xml

.PHONY: doc
doc:
	$(MAKE) -C doc/ html

.PHONY: man
man:
	$(MAKE) -C doc/ man
	cp doc/_build/man/flent.1 man/
