.PHONY: all install clean

ifdef RPM_OPTIMIZE
CCOPT	= $(RPM_OPTIMIZE)
else
CCOPT	= -Wall -O2 -g
endif

CFLAGS	= -D_GNU_SOURCE $(CCOPT) -I../library

all: curlies-test

curlies-test: curlies-test.c
	$(CC) $(CFLAGS) -o $@ curlies-test.c -L../library -lsusetest

install: ;

clean:
	rm -f *.o curlies-test
