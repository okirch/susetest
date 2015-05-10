
SUBDIRS	= minixml suselog susetest junit2

all install clean distclean::
	for dir in $(SUBDIRS); do make -C $$dir $@; done

