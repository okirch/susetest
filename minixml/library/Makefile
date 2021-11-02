include ../../Make.defs

TARGETS = \
	  libminixml.so

CFLAGS	= -fPIC $(CCOPT) -D_GNU_SOURCE
LIBOBJS	= xml.o \
	  xml-reader.o \
	  xml-writer.o \
	  util.o

VERSION = $(SUSETEST_VERSION)

all: $(TARGETS)

install: $(TARGETS)
	install -d $(DESTDIR)/usr/include
	install -d $(DESTDIR)/$(LIBDIR)
	install -m 555 libminixml.so $(DESTDIR)/$(LIBDIR)/libminixml.so.$(VERSION)

clean distclean::
	rm -f $(TARGETS) *.o
	rm -f test-report.xml

libminixml.so: $(LIBOBJS)
	$(CC) $(CFLAGS) -o $@ -shared -Wl,-soname,$@.$(VERSION) $(LIBOBJS)
	ln -sf $@ $@.$(VERSION)
