import sys

def obfuscate(source):
    """Currently just compile with optimization.

    Also remove .py files and rename optimized .pyo files as .pyc.
    """

    import os, re, subprocess

    pyfile_re = re.compile('.+\.py$')

    def _call(cmd):
        rv = subprocess.call(cmd)
        if rv != 0:
            raise Exception('failed command: %s, retval: %s' % (cmd, str(rv)))

    for root, dirs, files in os.walk(source):
        for f in files:
            m = pyfile_re.match(f)
            if m is None:
                continue

            fname = os.path.abspath(os.path.join(root, f))
            print "processing file: %s" % fname
            _call(['/bin/rm', '-f', '%sc' % fname, '%so' % fname])

    _call(['/usr/bin/python2.4', '-OO', '/usr/lib/python2.4/compileall.py', source])

    for root, dirs, files in os.walk(source):
        for f in files:
            m = pyfile_re.match(f)
            if m is None:
                continue

            fname = os.path.abspath(os.path.join(root, f))
            _call(['/bin/rm', '-f', '%sc' % fname])
            _call(['/bin/mv', '%so' % fname, '%sc' % fname])
            _call(['/bin/rm', '-f', fname])


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(2)

    obfuscate(sys.argv[1])
