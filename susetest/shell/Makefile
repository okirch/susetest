include ../../Make.defs

.PHONY: all install clean

CFLAGS	= -D_GNU_SOURCE $(CCOPT) \
	  $(TWOPENCE_CFLAGS)
LINK	+= -lcurlies

all: susetest

susetest: susetest.o config.o
	$(CC) $(CFLAGS) -o $@ susetest.o config.o $(LINK)

install: susetest
	mkdir -p $(DESTDIR)$(BINDIR)
	install -m555 susetest $(DESTDIR)$(BINDIR)/susetest

clean:
	rm -f susetest *.o

