include Make.defs

SUBDIRS	= python

HELPERS	= run-test list-platforms

all install clean distclean::
	set -e; for dir in $(SUBDIRS); do make -C $$dir $@; done

install::
	install -d $(DESTDIR)$(TWOPENCE_BINDIR)
	install -m555 $(HELPERS) $(DESTDIR)$(TWOPENCE_BINDIR)
