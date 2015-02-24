.PHONY: all install clean

ifdef RPM_OPT_FLAGS
CCOPT	= $(RPM_OPT_FLAGS)
else
CCOPT	= -Wall -O2 -g
endif

CFLAGS	= -D_GNU_SOURCE $(CCOPT) \
	  -I/usr/include/twopence \
	  -I../library
LINK	+= -L../library -lsusetest

BINDIR ?= /usr/bin
MANDIR ?= /usr/share/man

all: susetest

susetest: susetest.o config.o ../library/susetest.h
	$(CC) $(CFLAGS) -o $@ susetest.o config.o $(LINK)

install: susetest
	mkdir -p $(DESTDIR)$(BINDIR)
	install -m555 susetest $(DESTDIR)$(BINDIR)/susetest

clean:
	rm -f susetest *.o

