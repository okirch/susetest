
all install clean distclean tests::
	make -C src $@

install::
	install -d $(DESTDIR)/usr/bin
	install -m555 jlogger.sh $(DESTDIR)/usr/bin/jlogger
	install -d $(DESTDIR)/usr/share/susetest
	install -m444 USAGE.md $(DESTDIR)/usr/share/susetest/README.jlogger

tests::
	src/to_junit sample.log > report.xml
	xmllint --noout --schema JUnit.xsd report.xml 

doc:	junit.html

junit.html: junit.md
	markdown_py junit.md  > junit.html

clean::
	rm -f report.xml junit.html
