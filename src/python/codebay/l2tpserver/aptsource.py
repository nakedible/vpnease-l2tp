"""
Find and return cached apt sources.list.
"""

from codebay.l2tpserver import constants

# XXX: verify contents?

def get_cached_aptsource():
    sources = None

    f = None
    try:
        try:
            f = open(constants.APTSOURCE_CACHE, 'r')
            sources = f.read()
        except:
            sources = None
    finally:
        if f is not None: f.close()

    return sources

def get_current_aptsource():
    sources = None

    f = None
    try:
        try:
            f = open('/etc/apt/sources.list', 'r')
            sources = f.read()
        except:
            sources = None
    finally:
        if f is not None: f.close()

    return sources
    

def store_aptsource(sources):
    f = None
    try:
        try:
            f = open(constants.APTSOURCE_CACHE, 'w')
            f.write(sources)
        except:
            pass
    finally:
        if f is not None: f.close()
