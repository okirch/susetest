
CFLAGS	= -fPIC -I/usr/include/python -I../library -Wall -g

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
