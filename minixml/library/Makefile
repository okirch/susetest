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
	  libminixml.so

CFLAGS	= -fPIC $(CCOPT) -D_GNU_SOURCE
LIBOBJS	= xml.o \
	  xml-reader.o \
	  xml-writer.o \
	  util.o

MAJOR	= 0
MINOR	= 1
VERSION = $(MAJOR).$(MINOR)

all: $(TARGETS)

install: $(TARGETS)
	install -d $(DESTDIR)/usr/include
	install -d $(DESTDIR)/$(libdir)
	install -m 555 libminixml.so $(DESTDIR)/$(libdir)/libminixml.so.$(VERSION)
	ln -sf libminixml.so.$(VERSION) $(DESTDIR)/$(libdir)/libminixml.so.$(MAJOR)
	ln -sf libminixml.so.$(VERSION) $(DESTDIR)/$(libdir)/libminixml.so

clean distclean::
	rm -f $(TARGETS) *.o
	rm -f test-report.xml

libminixml.so: $(LIBOBJS)
	$(CC) $(CFLAGS) -o $@ -shared -Wl,-soname,$@.$(VERSION) $(LIBOBJS) -lncurses
	ln -sf $@ $@.$(VERSION)
