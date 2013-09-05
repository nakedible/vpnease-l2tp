#!/usr/bin/python

import re, os, tempfile
from subprocess import call

policy_match_re = re.compile(r'^(\d+\.\d+.\d+.\d+)\[(\d+)\] (\d+\.\d+\.\d+\.\d+)\[(\d+)\] udp\n\s+(\w+)\s+\.*refcnt=\d+\n')

"""
Example non-working left-over single policy (outbound this time):

172.20.12.3[1701] 84.240.69.164[4500] udp
        out prio high + 1073739744 ipsec
        esp/transport//require
        created: Mar 25 20:32:45 2009  lastused: Mar 25 21:31:00 2009
        lifetime: 0(s) validtime: 0(s)
        spid=89 seq=10 pid=32135
        refcnt=1
"""

# returns: src ip, src port, dst ip, dst port, direction
def find_suspectible_policies(policydump):
    outs = {}
    ins = {}
    
    for m in policy_match_re.search(policydump, re.M):
        src_ip = m.groups()[0]
        src_port = m.groups()[1]
        dst_ip = m.groups()[2]
        dst_port = m.groups()[3]
        dir = m.groups()[4]
        
        val = (src_ip, src_port, dst_ip, dir)

        if dir == 'in':
            key = '%s[%s]' % (src_ip, src_port)
            ins.put(key, val)
        else:
            key = '%s[%s]' % (dst_ip, dst_port)
            outs.put(key, val)

    suspects = []
    for k,v in outs.iteritems():
        if not ins.has_key(k):
            suspects.append(v)

    return suspects

def delete_policy(src_ip, src_port, dst_ip, dst_port, direction):
    f = tempfile.NamedTemporaryFile()
    try:
        cmd = '/usr/sbin/setkey'
        args = ['-f', f.name]

        script = ['spddelete',
                  '-4',
                  '%s[%s]' % (src_ip, src_port),
                  '%s[%s]' % (dst_ip, dst_port),
                  'any',
                  '-P',
                  direction,
                  ';\n'].join(' ')
        f.write(script)
        f.flush()

        return call([cmd] + args, close_fds=True, cwd='/tmp')
    finally:
        f.close()


# FIXME: actual cleanup logic here
# - when and how to run (cron, etc)
# - keep track of suspects (status db or internal if looping here?)
# - how to decide that single policy is permanent problem (multiple hits, etc?)
# - how to act if removing fails? (reboot, etc)

