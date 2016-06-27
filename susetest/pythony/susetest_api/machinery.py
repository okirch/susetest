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

        def run_control(self, cmd):
                subprocess.call(cmd, shell=True)

        def check_machinery(self):
                ''' this function ensure that machinery is installed on control node '''
                if not subprocess.call("which machinery", shell=True):
                        return True
                self.node.journal.fatal("ERROR, machinery is not installed on control node")
                return False

        def inspect(self):
                if self.check_machinery() != True:
                        return False
                self.node.journal.info("inspecting {}".format(self.node.name))
                self.run_control("machinery inspect {}".format(self.node.ipaddr))

        def show(self):
                self.run_control("machinery show --no-pager {}".format(self.node.ipaddr))
~                                                                                                                                                                                                                  
~                                                                                             
