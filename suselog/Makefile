
SUBDIRS	= library shell python

all install clean distclean::
	for dir in $(SUBDIRS); do make -C $$dir $@; done
