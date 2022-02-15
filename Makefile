include Make.defs

SUBDIRS	= python

HELPERS	= build-image run-test list-platforms

INSTALL	= install-helpers
CLEAN	=
ifeq ($(INSTALL_MANPAGES),true)
  INSTALL += install-man
  CLEAN += clean-man
endif
MAN1PAGES= $(patsubst %,man/twopence-%.1,$(HELPERS))

all install clean distclean::
	set -e; for dir in $(SUBDIRS); do make -C $$dir $@; done

install:: $(INSTALL)
clean:: $(CLEAN) ;

install-helpers:
	install -d $(DESTDIR)$(TWOPENCE_BINDIR)
	install -m555 $(HELPERS) $(DESTDIR)$(TWOPENCE_BINDIR)

install-man: $(MAN1PAGES)
	install -d -m755 $(DESTDIR)$(MANDIR)/man1
	install -m444 $(MAN1PAGES) $(DESTDIR)$(MANDIR)/man1

clean-man:
	rm -f man/*.[1-9]

man/%.1: man/%.1.in
	./microconf/subst $@
