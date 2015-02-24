# If we decide to use Qt5, we need to use
#   -I/usr/include/qt5 -fPIC
# and
#   -lQt5Xml -lQt5Core 
# instead.
QT_INC	= $(CCOPT)
QT_LIBS	= -lQtXml -lQtCore

ifdef RPM_OPT_FLAGS
CCOPT	= $(RPM_OPT_FLAGS)
else
CCOPT	= -Wall -O2 -g
endif

CXXFLAGS = $(CCOPT) $(QT_INC)
LDLIBS	= $(QT_LIBS)

OBJS	= main.o to_junit.o decomposition.o

all: to_junit

install: to_junit
	install -d $(DESTDIR)/usr/bin
	install -m555 to_junit $(DESTDIR)/usr/bin/

to_junit: $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $(OBJS) $(LDLIBS)

main.o: main.cpp to_junit.h decomposition.h
to_junit.o: to_junit.cpp to_junit.h decomposition.h
decomposition.o: decomposition.cpp to_junit.h decomposition.h

clean:
	rm -f to_junit
