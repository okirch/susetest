
SUBDIRS	= library shell python

all install clean distclean::
	set -e; for dir in $(SUBDIRS); do make -C $$dir $@; done

install::
	install -d $(DESTDIR)/usr/lib/susetest
	install -m555 runner $(DESTDIR)/usr/lib/susetest/runner
	install -d $(DESTDIR)/usr/share/susetest
	install -m444 HOWTO $(DESTDIR)/usr/share/susetest/README.config
