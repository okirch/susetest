include ../Make.defs

SUBDIRS	= shell python

HELPERS	= twopence-install twopence-run build-config

all install clean distclean::
	set -e; for dir in $(SUBDIRS); do make -C $$dir $@; done

install::
	install -d $(DESTDIR)$(SUSETEST_SCRIPT_DIR)
	install -m555 $(HELPERS) $(DESTDIR)$(SUSETEST_SCRIPT_DIR)
