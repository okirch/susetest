
SUBDIRS	= suselog junit2

all clean distclean::
	for dir in $(SUBDIRS); do make -C $$dir $@; done

