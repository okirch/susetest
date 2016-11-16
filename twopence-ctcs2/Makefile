BINDIR ?= /usr/bin

all:	twopence-ctcs2.py

distclean clean::
	:

distclean::
	rm -f test-junit.xml

install:
	install -d $(DESTDIR)$(BINDIR)
	install -m555 twopence-ctcs2.py $(DESTDIR)$(BINDIR)/twopence-ctcs2
