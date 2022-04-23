include Make.defs

INSTALL_MOD_DIR = $(PYTHON_INSTDIR)/susetest
SUBDIRS	= 

HELPERS	= build-image run-test run-suite list-platforms tabulate-results regress-results

INSTALL	= install-python install-helpers
CLEAN	=
BUILD	=
ifeq ($(INSTALL_MANPAGES),true)
  INSTALL += install-man
  CLEAN += clean-man
  BUILD += build-man
endif
MAN1PAGES= $(patsubst %,man/twopence-%.1,$(HELPERS))
MAN5PAGES= $(patsubst %.in,%,$(wildcard man/*.5.in))

all install clean distclean::
	set -e; for dir in $(SUBDIRS); do make -C $$dir $@; done

all:: $(BUILD) ;
install:: $(INSTALL) ;
clean:: $(CLEAN) ;

install-python:
	install -d $(DESTDIR)$(INSTALL_MOD_DIR)
	install -m444 python/susetest/*.py $(DESTDIR)$(INSTALL_MOD_DIR)

install-helpers:
	install -d $(DESTDIR)$(TWOPENCE_BINDIR)
	install -m555 $(HELPERS) $(DESTDIR)$(TWOPENCE_BINDIR)

build-man: $(MAN1PAGES)

install-man: $(MAN1PAGES) $(MAN5PAGES)
	install -d -m755 $(DESTDIR)$(MANDIR)/man1
	install -m444 $(MAN1PAGES) $(DESTDIR)$(MANDIR)/man1
	install -d -m755 $(DESTDIR)$(MANDIR)/man5
	install -m444 $(MAN5PAGES) $(DESTDIR)$(MANDIR)/man5

clean-man:
	rm -f man/*.[1-9]

man/%: man/%.in microconf/subst microconf/sedscript
	rm -f $@
	./microconf/subst $@
