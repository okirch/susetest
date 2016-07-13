#! /usr/bin/python

import susetest
import suselog
import traceback
import subprocess

# we need subprocess in case we run machinery from control-node, at the end is the most usefull place to run it.

# machinery api functions for susetest
class machinery:
        def __init__(self, node):
                self.node = node
                self.run_control("rm /var/lib/slenkins/.ssh/known_hosts")
     		self.check_ssh_config_control()
		self.system = ""
	def check_ssh_config_control(self):
		pass
 
	def run_control(self, cmd):
        	subprocess.call(cmd, shell=True)
        def check_machinery(self):
                ''' this function ensure that machinery is installed on control node '''
                if not subprocess.call("which machinery", shell=True):
                        return True
                self.node.journal.fatal("ERROR, machinery is not installed on control node")
                return False

        def inspect(self):
		if not self.node.desktop :
			variant = "-default"
		else :
			variant = "-gnome"
		self.system = self.node.build + variant 
 
                if self.check_machinery() != True:
                        return False
                # need for force machinery to work. 
                self.node.journal.info("inspecting {}".format(self.node.name))
                self.run_control("machinery inspect {}".format(self.node.ipaddr_ext))
		self.run_control("machinery move {0} {1}".format(self.node.ipaddr_ext, self.system))

        def show(self, suite_name, console=False):
                if not console :
                        self.run_control("machinery show --no-pager {} > $WORKSPACE/{}_machinery.txt".format(self.system, suite_name))
                else:
                        self.run_control("machinery show --no-pager {}".format(self.node.ipaddr_ext))

        def compare(self, system, console=False):
                '''system is like this SLE_12_SP2_Build1641-x86_64-default '''
                # get system
		if  not subprocess.call("machinery list --short | grep {0}".format(system)):
                	self.node.journal.info("comparing {}  with {}".format(self.node.name, system))
                	self.run_control("machinery compare {} {} --no-pager".format(self.system, system))

                self.run_control("mkdir /var/lib/slenkins/.machinery/{}".format(system))
                self.run_control("wget -O /var/lib/slenkins/.machinery/{0}/{0} http://slenkins/machinery/{0}.json; mv /var/lib/slenkins/.machinery/{0}/{0} /var/lib/slenkins/.machinery/{0}/manifest.json".format(system))

                self.node.journal.info("comparing {}  with {}".format(self.node.name, system))
                self.run_control("machinery compare {} {} --no-pager".format(self.node.ipaddr_ext, system))
