
SUBDIRS	= library python

all clean distclean::
	for dir in $(SUBDIRS); do make -C $$dir $@; done
