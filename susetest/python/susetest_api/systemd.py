#! /usr/bin/python

import susetest
import suselog
import traceback
import sys

class SYSTEMD(Exception):
                sys.exit(1)

class systemd(node):
        def __init__(self, node):
                self.node = node
                self.systemd = self.has_systemd()
                self.version = get_version()
                self.journal  = self.get_journal()

        def get_version():
            status = self.node.run("rpm -q systemd", timeout=200, quiet=True)
            if status.code != 0 and status != 0:
                        raise SYSTEMD("IMPOSSIBLE TO GET SYSTEMD VERSION ON NODE " + self.node)
            version = str(status.stdout).rstrip()
            return version

        def has_systemd():
            status = self.node.run("test -x /usr/bin/systemctl" , timeout=200, quiet=True)
            if status.code != 0 and status != 0:
                # init -> skip
                raise SYSTEMD("no systemd in node : " + self.node)
            return True

        # get the journal full for moment.
        def get_journal():
                status = self.node.run("journalctl -b -o json-pretty --no-pager", quiet=True, timeout=900)
                if status != 0 and status != 0:
                        raise SYSTEMD("Impossible to get journal from node" + self.node)
                journal = str(status.stdout)
                return journal

        # some function that manipulate the journal.
