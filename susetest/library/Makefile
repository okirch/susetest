.PHONY: all install clean

MAJOR	= 0
MINOR	= 1
VERSION	= $(MAJOR).$(MINOR)

ifdef RPM_OPTIMIZE
CCOPT	= $(RPM_OPTIMIZE)
else
CCOPT	= -Wall -O2 -g
endif

CFLAGS	= -D_GNU_SOURCE -fPIC $(CCOPT)

LIBDIR ?= /usr/lib64
INCDIR ?= /usr/include

LIB_OBJS= config.o \
	  curlies.o

all: libsusetest.so

libsusetest.so: susetest.h $(LIB_OBJS) Makefile
	$(CC) $(CFLAGS) -o $@ --shared -Wl,-soname,$@.$(VERSION) $(LIB_OBJS)

install: libsusetest.so susetest.h
	install -d $(DESTDIR)$(INCDIR)
	install -m444 susetest.h $(DESTDIR)$(INCDIR)
	install -d $(DESTDIR)$(LIBDIR)
	install -m555 libsusetest.so $(DESTDIR)$(LIBDIR)/libsusetest.so.$(VERSION)
	ln -sf libsusetest.so.$(VERSION) $(DESTDIR)/usr/lib64/libsusetest.so.$(MAJOR)
	ln -sf libsusetest.so.$(VERSION) $(DESTDIR)/usr/lib64/libsusetest.so


config.o: config.c susetest.h

clean:
	rm -f *.o *.so
