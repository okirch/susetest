include ../../Make.defs

.PHONY: all install clean

VERSION	= $(SUSETEST_VERSION)

CFLAGS	= -D_GNU_SOURCE -fPIC $(CCOPT) $(TWOPENCE_CFLAGS)

LIB_OBJS= config.o \
	  curlies.o

all: libsusetest.so

libsusetest.so: susetest.h $(LIB_OBJS) Makefile
	$(CC) $(CFLAGS) -o $@ --shared -Wl,-soname,$@.$(VERSION) $(LIB_OBJS) $(TWOPENCE_LIBS)

install: libsusetest.so susetest.h
	install -d $(DESTDIR)$(INCDIR)
	install -m444 susetest.h $(DESTDIR)$(INCDIR)
	install -d $(DESTDIR)$(LIBDIR)
	install -m555 libsusetest.so $(DESTDIR)$(LIBDIR)/libsusetest.so.$(VERSION)
	ln -sf libsusetest.so.$(VERSION) $(DESTDIR)/$(LIBDIR)/libsusetest.so


config.o: config.c susetest.h

clean:
	rm -f *.o *.so
