include Make.defs

SUBDIRS	= minixml suselog susetest twopence-ctcs2

all install clean distclean::
	set -e; for dir in $(SUBDIRS); do make -C $$dir $@; done

