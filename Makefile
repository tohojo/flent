PYTHON=python
PREFIX=/usr

all: build

build: flent/*.py
	$(PYTHON) setup.py build

.PHONY: install
install:
	$(PYTHON) setup.py install
	install -m 0644 -D -t $(PREFIX)/share/doc/flent BUGS README.rst *.example
	install -m 0644 -D -t $(PREFIX)/share/doc/flent/misc misc/*
	install -m 0644 -t $(PREFIX)/share/man/man1 man/flent.1
	install -m 0644 -t $(PREFIX)/share/mime/packages flent-mime.xml
	install -m 0644 -t $(PREFIX)/share/applications flent.desktop
