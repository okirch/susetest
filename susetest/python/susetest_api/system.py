#! /usr/bin/python

import susetest
import suselog
# needed by install_pkg 
from pipes import quote
from susetest_api.assertions import run_cmd
# needed by versioncmp
import re


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

## EASY-HACKS

# TODO: implement a function to start/stop/status of services that is initd/systemd indipendent
#      service(node, action, service) --> service(server, stop, postifix)

## TODO: implement functions that manipulete the machines.

# reboot(node)
# poweroff(node) -> simulate an unexpected shutdown

# TODO: implement snapper functions for backups 

## DIFFICULTY : HIGH -> utopic :)
## TODO: implement a function to spawn docker/systemd containers inside a sut. This will make like a datacenter inside a vm
#        like   spawn(type, number, os).  spawn(systemd, 10, SLE-12-SP2). this will create  10 systemd-containers inside the node.
