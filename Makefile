
SUBDIRS	= minixml suselog susetest twopence-ctcs2

all install clean distclean::
	for dir in $(SUBDIRS); do make -C $$dir $@; done

