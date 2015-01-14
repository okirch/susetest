
CFLAGS	= -fPIC -I/usr/include/python2.6 -I../library -Wall -g

PYDIR  ?= /usr/lib64/python2.6/site-packages

all:	suselog.so

suselog.so: extension.o
	$(CC) --shared -o $@ extension.o -L../library -lsuselog

distclean clean::
	rm -f *.o *.so

distclean::
	rm -f test-report.xml

install:
	mkdir -p $(DESTDIR)$(PYDIR)
	cp suselog.so $(DESTDIR)$(PYDIR)
