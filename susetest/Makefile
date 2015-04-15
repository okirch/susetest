
SUBDIRS	= library shell python tests

HELPERS	= twopence-install twopence-run build-config

all install clean distclean::
	set -e; for dir in $(SUBDIRS); do make -C $$dir $@; done

install::
	install -d $(DESTDIR)/usr/lib/susetest
	install -m555 $(HELPERS) $(DESTDIR)/usr/lib/susetest
	install -d $(DESTDIR)/usr/share/susetest
	install -m444 HOWTO $(DESTDIR)/usr/share/susetest/README.config
