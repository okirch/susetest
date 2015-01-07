all: to_junit

to_junit: main.cpp to_junit.cpp to_junit.h decomposition.cpp decomposition.h
	g++ main.cpp to_junit.cpp decomposition.cpp \
		-fPIC \
		-I /usr/include/qt5 \
		-l Qt5Xml -l Qt5Core \
		-o to_junit

clean:
	rm -f to_junit
