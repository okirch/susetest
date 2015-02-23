
TARGETS = \
	  libsuselog.so \
	  test-logging \
	  test-junit

CFLAGS	= -fPIC -Wall -g -D_GNU_SOURCE
LIBOBJS	= suselog.o \
	  util.o \
	  xml.o \
	  xml-reader.o \
	  xml-writer.o

MAJOR	= 0
MINOR	= 1
VERSION = $(MAJOR).$(MINOR)

all: $(TARGETS)

install: $(TARGETS)
	install -d $(DESTDIR)/usr/include
	install -m 444 suselog.h $(DESTDIR)/usr/include
	install -d $(DESTDIR)/usr/lib64
	install -m 555 libsuselog.so $(DESTDIR)/usr/lib64/libsuselog.so.$(VERSION)
	ln -sf libsuselog.so.$(VERSION) $(DESTDIR)/usr/lib64/libsuselog.so.$(MAJOR)
	ln -sf libsuselog.so.$(VERSION) $(DESTDIR)/usr/lib64/libsuselog.so

clean distclean::
	rm -f $(TARGETS) *.o
	rm -f test-report.xml

libsuselog.so: $(LIBOBJS)
	$(CC) $(CFLAGS) -o $@ -shared -Wl,-soname,$@.$(VERSION) $(LIBOBJS)

suselog.o: suselog.c suselog.h suselog_p.h
	$(CC) $(CFLAGS) -c -o $@ suselog.c

test-logging: test-logging.o libsuselog.so
	$(CC) -o $@ test-logging.o -L. -lsuselog

testit.o: testit.c suselog.h
	$(CC) $(CFLAGS) -c -o $@ testit.c 

test-junit: test-junit.o libsuselog.so
	$(CC) -o $@ test-junit.o -L. -lsuselog

test-junit.o: test-junit.c suselog.h
	$(CC) $(CFLAGS) -c -o $@ test-junit.c 
