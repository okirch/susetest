.PHONY: all install clean

ifdef RPM_OPT_FLAGS
CCOPT	= $(RPM_OPT_FLAGS)
else
CCOPT	= -Wall -O2 -g
endif

CFLAGS	= -D_GNU_SOURCE $(CCOPT) -I../library

all: curlies-test

curlies-test: curlies-test.c
	$(CC) $(CFLAGS) -o $@ curlies-test.c -L../library -lsusetest -L../../minixml/library -lminixml

install: ;

clean:
	rm -f *.o curlies-test
