all: check

check:
	make -C src
	src/to_junit sample.log > report.xml
	xmllint --noout --schema JUnit.xsd report.xml 

doc:	junit.md
	markdown_py junit.md  > junit.html

clean:
	make -C src clean
	rm -f report.xml junit.html
