#! /usr/bin/python

import susetest
import suselog
# needed by install_pkg 
from pipes import quote
from susetest_api.assertions import run_cmd
# needed by versioncmp
import re
# needed by reboot_and_wait
import os
import time


# Thx to Aurelien Aptel, Samba Dev.
def install_pkg(node, package):
    """On @node, install @package.

    @package can a string or a list of string e.g. "foo" or ["foo", "bar"].
    """
    if isinstance(package, list):
        package = ' '.join([quote(x) for x in package])
    elif isinstance(package, str):
        package = quote(package)
    else:
        # type error
        raise susetest.SlenkinsError(1)
    run_cmd(node, "zypper -n --gpg-auto-import-keys ref && zypper -n in %s" % package, "installing package")


# Compares the version of package installed on node
# Example:
# ret = versioncmp(host, "shadow", "4.2.1")
# if ret == "<": # meaning if installed version is older than 4.2.1
def versioncmp(node, package, version):
    status = node.run("rpm -qi " + package, quiet=True)
    if status.code == 1:
        node.journal.failure("rpm -qi " + package + "failed")
        return

    line = str(status.stdout)
    installed_version = re.findall(r"Version +: (.+?)\n", line)[0]

    if installed_version:
        status = node.run("zypper versioncmp " + installed_version + " " + version, quiet=True)
        if status.code != 0:
            node.journal.failure("zypper versioncmp failed")
            return

        comparison = str(status.stdout)

        if "matches" in comparison:
            return "="
        elif "newer" in comparison:
            return ">"
        elif "older" in comparison:
            return "<"


# Reboot a node and wait until it's back
def reboot_and_wait(node):
   # 1. Trigger reboot
   addr = node.ipv4_addr
   opt = "-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
   os.system("ssh {} root@{} \"reboot >/dev/null 2>/dev/null\"".format(opt, addr))

   # 2. Wait for system to stop answering pings
   c = 0
   while os.system("ping -q -c1 {}".format(addr)) == 0 and c < 60:
      time.sleep(1)
      c += 1

   # 3. Wait for system to restart answering pings
   c = 0
   while os.system("ping -q -c1 {}".format(addr)) != 0 and c < 60:
      time.sleep(1)
      c += 1

   # 4. Wait for system to restart executing SSH commands
   c = 0
   while os.system("ssh {} root@{} \"whoami\"".format(opt, addr)) != 0 and c < 60:
      time.sleep(1)
      c += 1


## EASY HACKS
# TODO: implement a function to start/stop/status of services that is initd/systemd independent
#       service(node, action, service) --> service(server, stop, postifix)

# TODO: poweroff(node) -> simulate an unexpected shutdown

# TODO: implement snapper functions for backups 

## DIFFICULTY : HIGH -> utopic :)
# TODO: implement a function like spawn(node, type, number, os) to spawn docker/systemd containers inside a sut.
#       This will make a kind of datacenter inside a vm.
#       For example, spawn(sut, systemd, 10, SLE_12_SP2) will create 10 systemd containers inside the node.
