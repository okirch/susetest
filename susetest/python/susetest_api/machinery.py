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
		self.system = self.get_system()
		# FIXME: find a method to find out automatically the suite name.
	        self.suite_name = ""

	def check_ssh_config_control(self):
		''' we should check that ssh/.config containt no checks, otherwise set it '''
		pass
 
	def run_control(self, cmd):
        	subprocess.call(cmd, shell=True)
        def check_machinery(self):
                ''' this function ensure that machinery is installed on control node '''
                if not subprocess.call("which machinery", shell=True):
                        return True
                self.node.journal.fatal("ERROR, machinery is not installed on control node")
                return False

	def get_system(self):
		if not self.node.desktop :
			variant = "-default"
		else :
			variant = "-gnome"
		return self.node.build + variant 

        def inspect(self):

                if self.check_machinery() != True:
                        return False
                # need for force machinery to work. 
                self.node.journal.info("inspecting {}".format(self.node.name))
                self.run_control("machinery inspect {}".format(self.node.ipaddr_ext))
		self.run_control("machinery move {0} {1}".format(self.node.ipaddr_ext, self.system))
        def show(self, suite_name, console=False):
                if not console :
			self.suite_name = suite_name
                        self.run_control("machinery show --no-pager {} > $WORKSPACE/{}_machinery.txt".format(self.system, suite_name))
                else:
                        self.run_control("machinery show --no-pager {}".format(self.node.ipaddr_ext))
        def compare(self, system, console=False):
                ''' compare always compare the node, and a system given from user(in testsuite)
		system is like this SLE_12_SP2_Build1641-x86_64-default
		'''
		# get system to compare from env.variable (jenkins
		if  not subprocess.call("machinery list --short | grep {0}".format(system), shell=True):
                	self.node.journal.info("comparing {}  with {}".format(self.node.name, system))
                	self.run_control("machinery compare {} {} --no-pager > $WORKSPACE/{}_machinery_cmp".format(self.system, system, self.suite_name))
			return True
		self.node.journal.info("no description of systems found ! ")
		return False
