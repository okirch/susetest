include ../../Make.defs

CFLAGS	= -fPIC $(CCOPT) $(PYTHON_CFLAGS) -I../library

OBJS	= extension.o

all:	suselog.so

suselog.so: extension.o
	$(CC) --shared -o $@ extension.o -L../library -lsuselog

distclean clean::
	rm -f *.o *.so

distclean::
	rm -f test-report.xml

install:
	install -d $(DESTDIR)$(PYTHON_INSTDIR)
	install -m555 suselog.so $(DESTDIR)$(PYTHON_INSTDIR)
