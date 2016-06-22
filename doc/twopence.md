Twopence and susetest
=====================================================================

Twopence provides a generic layer for test scripts for communication with
nodes (SUT aka System Under Test). It is important to understand that in the
twopence model of operation, there is always an idependent control node that
orchestrates the test between the SUTs.

Where that control node resides, and what exactly it looks like, depends
on the environment you test in. If you test locally using KVM, then the
SUTs would be KVM guests and the control script would run on the host side.
If you run your tests under jenkins, then the SUTs might be VMs running in an
OpenStack clould while the control script runs on the jenkins host itself. In
an OpenQA environment, the control node might actually be in a separate VM.

The basic operations that twopence can provide are execution of commands,
as well as upload and download of files. So, a bit like what ssh will do for
you, except it's a bit more convenient to use and actually supports several
different modes of transport.  Twopence also provides shell commands as well
as a python and a ruby binding.

But, in a nutshell, twopence is the communication layer.


### susetest
Susetest sits on top of twopence and provides a convenience layer for test
scripts written in python.  Apart from offering a (small, so far) library of
helper functions, susetest provides logging facilities, and a simple interface
for constructing python objects for talking to the SUTs needed by your test.
