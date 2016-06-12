#!/usr/bin/python


# **********************************************************
# file operation for suse_test in multiple machine context.
#***********************************************************

# 1) replace_string 
# EXAMPLE:

# apache2_conf = {'OLD_STRING':'NEW_STRING', 'apache233':'hello_APACHE24444!', ' AllowOverride None':' AllowOverride Yes'}
# replace_string(server, apache2_conf, "httpd.conf", max_replace)

# If the optional argument maxreplace is given, the first maxreplace occurrences are replaced.
# otherwise  all patterns replaced

def replace_string(node, replacements, _file, _max_replace=0):
        ''' replace given strings as dict in the file '''
        data = node.recvbuffer(_file)
        if not data:
                node.journal.fatal("something bad with getting the file {}!".format(_file))
      		return False
        data_str = str(data)
        for src, target in replacements.iteritems():
                if not _max_replace:
                        data_str = data_str.replace(str(src), str(target))
                else:
                        data_str = data_str.replace(str(src), str(target), _max_replace)
        if not node.sendbuffer(_file,  bytearray(data_str)):
                node.journal.fatal("error writing file {}".format(_file))
 	        return False 
        return True

### TODO: add function that add text in file, to specific position in file. ( after a pattern, or in a line, etc)

# node -> node type susetest, strings -> dictionary of strings/text to be added
# _file -> file where to add strings
# methot do insert stings-> with line number or after a pattern, etc

def addString_file(node, strings, _file, methodTO_INSERT_STRING):
	pass
