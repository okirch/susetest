.PHONY: all install clean

VERSION	= 0.1.0

ifdef RPM_OPTIMIZE
CCOPT	= $(RPM_OPTIMIZE)
else
CCOPT	= -Wall -O2 -g
endif

CFLAGS	= -D_GNU_SOURCE -fPIC $(CCOPT)

LIBDIR ?= /usr/lib64
INCDIR ?= /usr/include

LIB_OBJS= config.o

all: libsusetest.so

libsusetest.so: susetest.h $(LIB_OBJS) Makefile
	$(CC) $(CFLAGS) -o $@ --shared -Wl,-soname,libsusetest.so.0 $(LIB_OBJS)

install: libsusetest.so susetest.h
	mkdir -p $(DESTDIR)$(LIBDIR)
	install -m555 libsusetest.so $(DESTDIR)$(LIBDIR)/libsusetest.so.$(VERSION)
	mkdir -p $(DESTDIR)$(INCDIR)
	install -m444 susetest.h $(DESTDIR)$(INCDIR)

config.o: config.c susetest.h

clean:
	rm -f *.o *.so
