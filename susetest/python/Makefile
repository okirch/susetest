
ifdef RPM_OPT_FLAGS
CCOPT	= $(RPM_OPT_FLAGS)
else
CCOPT	= -Wall -O2 -g
endif

CFLAGS	= -D_GNU_SOURCE -fPIC $(CCOPT) \
	  -I/usr/include/twopence \
	  -I/usr/include/python \
	  -I../library

PYDIR  := $(shell readlink -f /usr/lib64/python/site-packages)

OBJS	= extension.o \
	  config.o

all:	susetest.so

susetest.so: $(OBJS)
	$(CC) --shared -o $@ $(OBJS) -L../library -lsusetest

distclean clean::
	rm -f *.o *.so

distclean::
	;

install:
	mkdir -p $(DESTDIR)$(PYDIR)
	install -m555 susetest.so $(DESTDIR)$(PYDIR)
