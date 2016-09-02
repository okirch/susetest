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

CFLAGS	= -fPIC $(CCOPT) -I/usr/include/python -I../library

PYDIR  := $(shell readlink -f /$(libdir)/python/site-packages)

OBJS	= extension.o

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
