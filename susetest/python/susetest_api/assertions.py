#! /usr/bin/python

import susetest
import suselog
import traceback

# Basic run command and consider it as a test.

#  run_cmd(server, "uptime && ls -a", "HELLO_WORLD_TEST", time_out = 200)
def run_cmd(node, command, msg, time_out = 60):
	''' exec command on node, with msg (fail/succ message for journal)
	    and use tiimeout = 60 as default, but as optional param. so can be modified.''' 
        node.journal.beginTest("{}".format(msg))
        status = node.run(command, timeout = time_out)
	if not status and status.code != 0 : 
               node.journal.failure("{} FAIL!".format(msg))
               return False
        node.journal.success("{} OK! ".format(msg))
        return True

#this expetion need to be cached.
def runOrRaise(node, command, msg, time_out = 60):
        ''' exec command on node, with msg (fail/succ message for journal)
            and use tiimeout = 60 as default, but as optional param. so can be modified.'''
        node.journal.beginTest("{}".format(msg))
        status = node.run(command, timeout = time_out)
        if not status and status.code != 0 :
               node.journal.failure("{} FAIL!".format(msg))
               raise susetest.SlenkinsError(1)
        node.journal.success("{} OK! ".format(msg))
        return True

########## ASSERTIONS ########################

# assert_equal(server, "su tomcat -c \"whoami\"", "tomcat")
def assert_ok_equal(node, command, expected):
        ''' this function catch the output of sucesseful command and expect a result string
        it check that a command success with something as string.'''
        node.journal.beginTest("for successful cmd: \"{}\" ASSERT_OUTPUT:  \"{}\" ".format(command, expected))

        status = node.run(command)
        if not (status):
                node.journal.failure("FAILURE: something unexpected!!{}".format(command))
                return False
        # check code exit of command.
        if (status.code != 0):
                node.journal.failure("COMMAND returned \"{}\" EXPECTED 0".format(str(status.code)) )
        # check output of  command.
        s = str(status.stdout)
        s = s.rstrip()
        if  (expected in s):
                node.journal.success("ASSERT_TEST_EQUAL to {} PASS! OK".format(command))
                return True
        else :
                node.journal.failure("GOT Output:\"{}\",  EXPECTED\"{}\"".format(s, expected))
	        return False

# assert_fail_equal(sut, "zypper lifecycle IAM_NOT_EXISTING_PACKAGE;", 2 "SKIP")
def assert_fail_equal(node, command, code,  expected="SKIP"):
        ''' this function catch the output of failed command and expect a result string
        it check that a command fail with something as string.
	by default we don't check the string returned by cmd, only the return_code'''
	if ( expected != "SKIP"):
     		  node.journal.beginTest("command \"{}\" should fail with this err Mess \"{}\" and errcode \"{}\" ".format(command, expected, code))
	else : 
		  node.journal.beginTest("command \"{}\" should fail with retcode : \"{}\"".format(command, code))

        if ( type(code) is str):
                node.journal.fatal("please insert a integer for variable code !")
        status = node.run(command)
        if (status and status.code != code):
                node.journal.failure("COMMAND returned error_code\"{}\" not as EXPECTED error_code  \"{}\" FAIL !!".format(str(status.code), str(code)) )
	        return False
        # if skip then skip output check
        if not ( expected == "SKIP"):
            # check output of failed command.
            s = str(status.stdout)
            if  (expected in s):
                   node.journal.success("Command failed as with retcode {0} as EXPECTED !  {1} PASS! OK".format(code, command))
                   return True
            else :
                node.journal.failure("GOT \"{}\",  EXPECTED\"{}\"".format(s, expected))
                return False

def fail_retcode(node, command, code):
        ''' this function expected that the command under test fail with the integer given as ret_code'''
        node.journal.beginTest("Command must fail \"{}\" with retcode\"{}\" ".format(command, expected))
        if not type(code) is int:
                node.journal.fatal("please insert a integer for variable code !")
                return False
        status = node.run(command, timeout=500)
        if (status and status.code != code):
                node.journal.failure("Command error_code\"{0}\" expected retcode: \"{}\". TEST_FAIL!!".format(str(status.code), str(code)) )
                return False
        node.journal.success("Command failed with retcode \"{0}\" as expected  \"{1}\" PASS! OK".format(code, command))
        return True
