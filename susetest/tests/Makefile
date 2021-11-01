include ../../Make.defs

.PHONY: all install clean

CFLAGS	= -D_GNU_SOURCE $(CCOPT) -I../library

all: curlies-test

curlies-test: curlies-test.c
	$(CC) $(CFLAGS) -o $@ curlies-test.c -L../library -lsusetest -L../../minixml/library -lminixml

install: ;

clean:
	rm -f *.o curlies-test
