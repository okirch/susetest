
import susetest
import suselog
import traceback

class SYSTEMD_ERR(Exception):
	pass

class systemd():
        def __init__(self, node):
                self.node = node
                self.systemd = self.has_systemd()
                self.version = self.get_version()
                self.journal  = self.get_journal()
		self.journal_prio = self.check_journal()
        def get_version(self):
            status = self.node.run("rpm -q systemd", timeout=200, quiet=True)
            if status.code != 0 and status != 0:
                        raise SYSTEMD("IMPOSSIBLE TO GET SYSTEMD VERSION ON NODE " + self.node.name)
            version = str(status.stdout).rstrip()
            return version

        def has_systemd(self):
            status = self.node.run("test -x /usr/bin/systemctl" , timeout=200, quiet=True)
            if status.code != 0 and status != 0:
                # init -> skip
                raise SYSTEMD_ERR("no systemd in node : " + self.node.name)
            return True

        # get the journal full for moment.
        def get_journal(self):
		""" get full journal"""
                status = self.node.run("journalctl -b --no-pager", quiet=True, timeout=900)
                if status.code != 0 and status != 0:
                        raise SYSTEMD_ERR("Impossible to get journal from node :" + self.node.name)
                journal = str(status.stdout)
                return journal

	def get_prio(self, prio):
		""" get prioritized journal, not full"""
		status = self.node.run("journalctl -b -p{0} --no-pager".format(prio), quiet=True, timeout=900)
                if status.code != 0 and status != 0:
                        raise SYSTEMD_ERR("Impossible to get journal from node" + self.node.name)
                journal_prio = str(status.stdout)
                return journal_prio

	def check_journal(self, prio_default=4):
		""" check systemd journal from p1 to p3 errors. with ignore"""
		prio_journal = []
		for prio in range(0, prio_default):
			prio_journal.append(self.get_prio(prio))
		return prio_journal
        # some function that manipulate the journal.

