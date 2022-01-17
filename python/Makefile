include ../Make.defs

SUSETEST_PYTHON_DIR = $(PYTHON_INSTDIR)/susetest

all: ;

distclean clean::
	rm -f *.o *.so
	rm -rf */__pycache__

distclean::
	;

install:
	mkdir -p $(DESTDIR)$(SUSETEST_PYTHON_DIR)
	install -m444 susetest/*.py $(DESTDIR)$(SUSETEST_PYTHON_DIR)
