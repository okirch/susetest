include ../../Make.defs

CFLAGS	= -D_GNU_SOURCE -fPIC $(CCOPT) \
	  $(TWOPENCE_CFLAGS) \
	  $(PYTHON_CFLAGS) \
	  -I../library

OBJS	= extension.o \
	  config.o

all:	curly.so susetest.py

curly.so: $(OBJS)
	$(CC) --shared -o $@ $(OBJS) -L../library -lsusetest

distclean clean::
	rm -f *.o *.so

distclean::
	;

install: curly.so susetest.py
	mkdir -p $(DESTDIR)$(PYTHON_INSTDIR)/susetest_api
	install -m555 curly.so $(DESTDIR)$(PYTHON_INSTDIR)
	install -m555 susetest.py $(DESTDIR)$(PYTHON_INSTDIR)
	install -m555 susetest_api/*.py $(DESTDIR)$(PYTHON_INSTDIR)/susetest_api
