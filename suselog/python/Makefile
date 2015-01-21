
CFLAGS	= -fPIC -I/usr/include/python2.6 -I../library -Wall -g

PYDIR  := $(shell readlink -f /usr/lib64/python/site-packages)

all:	suselog.so

suselog.so: extension.o
	$(CC) --shared -o $@ extension.o -L../library -lsuselog

distclean clean::
	rm -f *.o *.so

distclean::
	rm -f test-report.xml

install:
	install -d $(DESTDIR)$(PYDIR)
	install -m555 suselog.so $(DESTDIR)$(PYDIR)
