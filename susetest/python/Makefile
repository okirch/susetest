include ../../Make.defs

all:	susetest.py

distclean clean::
	rm -f *.o *.so

distclean::
	;

install: susetest.py
	mkdir -p $(DESTDIR)$(PYTHON_INSTDIR)/susetest_api
	install -m555 susetest.py $(DESTDIR)$(PYTHON_INSTDIR)
	install -m555 susetest_api/*.py $(DESTDIR)$(PYTHON_INSTDIR)/susetest_api
