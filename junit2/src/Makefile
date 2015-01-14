# If we decide to use Qt5, we need to use
#   -I/usr/include/qt5 -fPIC
# and
#   -lQt5Xml -lQt5Core 
# instead.
CXXFLAGS = -Wall
LDLIBS	= -lQtXml -lQtCore

OBJS	= main.o to_junit.o decomposition.o

all: to_junit

to_junit: $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $(OBJS) $(LDLIBS)

main.o: main.cpp to_junit.h decomposition.h
to_junit.o: to_junit.cpp to_junit.h decomposition.h
decomposition.o: decomposition.cpp to_junit.h decomposition.h

clean:
	rm -f to_junit
