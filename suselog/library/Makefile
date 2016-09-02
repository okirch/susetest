ifdef RPM_OPT_FLAGS
CCOPT	= $(RPM_OPT_FLAGS)
else
CCOPT	= -Wall -O2 -g
endif

MACHINE := $(shell uname -m)

ifeq ($(MACHINE), i686)
libdir = /usr/lib
else
libdir = /usr/lib64
endif

TARGETS = \
	  libsuselog.so \
	  test-logging \
	  test-junit

CFLAGS	= -fPIC $(CCOPT) -D_GNU_SOURCE -I../../minixml/library
LIBOBJS	= suselog.o

LINK	= -L../library -lsuselog -L../../minixml/library -lminixml

MAJOR	= 0
MINOR	= 1
VERSION = $(MAJOR).$(MINOR)

all: $(TARGETS)

install: $(TARGETS)
	install -d $(DESTDIR)/usr/include
	install -m 444 suselog.h $(DESTDIR)/usr/include
	install -d $(DESTDIR)/$(libdir)
	install -m 555 libsuselog.so $(DESTDIR)/$(libdir)/libsuselog.so.$(VERSION)
	ln -sf libsuselog.so.$(VERSION) $(DESTDIR)/$(libdir)/libsuselog.so.$(MAJOR)
	ln -sf libsuselog.so.$(VERSION) $(DESTDIR)/$(libdir)/libsuselog.so

clean distclean::
	rm -f $(TARGETS) *.o
	rm -f test-report.xml

libsuselog.so: $(LIBOBJS)
	$(CC) $(CFLAGS) -o $@ -shared -Wl,-soname,$@.$(VERSION) $(LIBOBJS) -lncurses -L../../minixml/library -lminixml

suselog.o: suselog.c suselog.h suselog_p.h
	$(CC) $(CFLAGS) -c -o $@ suselog.c

test-logging: test-logging.o libsuselog.so
	$(CC) -o $@ test-logging.o $(LINK)

testit.o: testit.c suselog.h
	$(CC) $(CFLAGS) -c -o $@ testit.c 

test-junit: test-junit.o libsuselog.so
	$(CC) -o $@ test-junit.o $(LINK)

test-junit.o: test-junit.c suselog.h
	$(CC) $(CFLAGS) -c -o $@ test-junit.c 
