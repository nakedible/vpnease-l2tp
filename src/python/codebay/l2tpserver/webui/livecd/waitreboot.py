"""Wait reboot page."""
__docformat__ = 'epytext en'

import formal
from twisted.internet import reactor, defer
from nevow import inevow, loaders, rend, url, tags as T

from codebay.l2tpserver.webui import commonpage
from codebay.nevow.formalutils import formalutils
from codebay.l2tpserver import constants
from codebay.l2tpserver import db
from codebay.l2tpserver.installer import installhelpers

class WaitRebootPage(formal.ResourceMixin, commonpage.LiveCdPage):
    template = 'livecd/waitreboot.xhtml'
    pagetitle = u'Rebooting'
    
    def macro_content_left(self, ctx):
        return ''
    
    def render_start_reboot_process(self, ctx, data):
        """Live CD eject and reboot process.

        This is rather tricky.  We don't want to use the normal Live CD reboot
        process, because the CD is ejected only after shutdown, which is a bad
        use case.  Instead, we forcibly eject the CD (a forced umount is not
        possible, but a forced eject is).  Before that, we warm up the necessary
        reboot commands so that they are in memory and the CD is not required.
        """

        stage1_delay = constants.LIVECD_FORCED_REBOOT_STAGE1_DELAY
        stage2_delay = constants.LIVECD_FORCED_REBOOT_STAGE2_DELAY

        # XXX: force_reboot_host() uses run_command

        def _reboot(res):
            print 'render_start_reboot_process: _reboot'
            installhelpers.force_reboot_host()
        @db.transact()
        def _stage2():
            print 'render_start_reboot_process: creating stage 2 deferred'
            d = defer.Deferred()
            d.addCallback(_reboot)
            d.callback(None)
            
        def _sync_disks(res):
            print 'render_start_reboot_process: _sync_disks'
            installhelpers.do_sync()
        def _warmup(res):
            print 'render_start_reboot_process: _warmup'
            installhelpers.cache_reboot_command()
        def _eject(res):
            print 'render_start_reboot_process: _eject'
            installhelpers.force_eject_cdrom()
        def _schedule_stage2(res):
            print 'render_start_reboot_process: starting stage 2 in %s seconds' % stage2_delay
            reactor.callLater(stage2_delay, _stage2)
        @db.transact()
        def _stage1():
            print 'render_start_reboot_process: creating stage 1 deferred'
            d = defer.Deferred()
            d.addCallback(_sync_disks)
            d.addCallback(_warmup)
            d.addCallback(_eject)
            d.addCallback(_schedule_stage2)
            d.callback(None)
        
        print 'render_start_reboot_process: starting stage 1 in %s seconds' % stage1_delay
        reactor.callLater(stage1_delay, _stage1)
        return ''
