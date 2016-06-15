#! /usr/bin/python

import susetest
import suselog
import traceback

#
def has_systemd(node):
        if not hasattr(node, "__has_systemd"):
                node.__has_systemd = False
                if node.run("test -x /usr/bin/systemctl"):
                        node.__has_systemd = True
        return node.__has_systemd

# TODO: implement an initd check (?)
#
# systemd_check(server, prio_default=5)
def systemd_check(node, prio_default=4):
    # jounrnalctl is strange, it behave different:
    # sometimes in early version it print date in first line sometimes not. 
    system_journal = "LINES=`journalctl -p{0} | wc -l`; if [ $LINES -ge 2 ]; then journalctl -p{0}; exit 1; else journalctl -p{0};  exit 0; fi"
    node.journal.beginGroup("systemd basic checks")
    for prio in range(1, prio_default):
         # systemd/journalctl return 1 when it found no log. so we have to cheat to make the inverse. 
         # ge is greater than or equal to --> >=
	 node.journal.beginTest("check systemd logs for PRIO: {}".format(prio))
	 status = node.run(system_journal)
	 if not status and status.code != 0 : 
                node.journal.failure("systemd check for PRIO: {} FAIL!".format(prio))
                return False
         node.journal.success("journalctl PRIO {} check : OK! ".format(prio))
    return True

# TODO: implement a function that check specific logs files for specific patterns.

