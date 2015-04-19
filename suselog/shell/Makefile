.PHONY: all install clean

ifdef RPM_OPT_FLAGS
CCOPT	= $(RPM_OPT_FLAGS)
else
CCOPT	= -Wall -O2 -g
endif

CFLAGS	= -D_GNU_SOURCE $(CCOPT) \
	  -I/usr/include/twopence \
	  -I../library
LINK	+= -L../library -lsuselog

BINDIR ?= /usr/bin
MANDIR ?= /usr/share/man

all: suselog

suselog: suselog.o ../library/suselog.h
	$(CC) $(CFLAGS) -o $@ suselog.o $(LINK)

install: suselog
	mkdir -p $(DESTDIR)$(BINDIR)
	install -m555 suselog $(DESTDIR)$(BINDIR)/suselog

clean:
	rm -f suselog *.o

