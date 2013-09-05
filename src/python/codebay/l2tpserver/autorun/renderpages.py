"""Helper for rendering autorun README html files statically during build.

Requires a Nevow installation on the build machine.  Assumes that working
directory is 'webui-pages'.  Resulting files are generated into a directory
named 'generated' from which the build system should then pick up any
necessary files.

XXX: This is currently executed manually.  Build takes two zipfiles from
the Subversion repository as inputs to build.  Use the following commands
to regenerate the zipfiles:

  $ cd l2tp-dev/src/python/webui-pages
  $ PYTHONPATH=:../ python ../codebay/l2tpserver/autorun/renderpages.py
  $ cp generated/autorun-installed.zip autorun-installed-files.zip
  $ cp generated/autorun-livecd.zip autorun-livecd-files.zip
  $ svn commit -m <message> autorun-*-files.zip
  $ rm -rf generated
"""

import os, textwrap

from nevow import inevow, loaders, rend

from codebay.l2tpserver import constants

class _StaticRender(rend.Page):
    docFactory = loaders.xmlfile('autorunpage.xhtml')
    contentfile = None
    pagetitle = 'No Title'
    
    def __init__(self):
        pass

    def render_page_title(self, ctx, data):
        return self.pagetitle

    def render_legal_notice_uri(self, ctx, data):
        return constants.PRODUCT_WEB_SERVER_ADDRESS

    def macro_productname(self, ctx):
        return constants.PRODUCT_NAME
    
    def macro_content(self, ctx):
        return loaders.xmlfile(self.contentfile, pattern='content')

class AutorunInstalledReadmePage(_StaticRender):
    pagetitle = 'VPNease Server'
    contentfile = 'autorun-installed/readme-template.xhtml'

class AutorunLivecdReadmePage(_StaticRender):
    pagetitle = 'Live CD'
    contentfile = 'autorun-livecd/readme-template.xhtml'

# --------------------------------------------------------------------------

class AutorunZipHelper:
    def __init__(self):
        pass

    def _add_other_files_livecd(self, destdir):
        autorun_dir = 'VPNease'  # XXX: constants
        autorun_readme_html = 'README.htm'
        autorun_ico = 'autorun.ico'

        lnx_autorun_script = 'autorun'
        win_autorun_inf = 'Autorun.inf'
        win_autorun_inf_contents = textwrap.dedent("""\
        [autorun]
        shellexecute=%(autorun_htm)s
        icon=%(autorun_ico)s
        action=VPNease
        label=VPNease Live CD
        """) % {'autorun_ico': '%s\\autorun.ico' % autorun_dir,
                'autorun_htm': autorun_readme_html}
        win_autorun_inf_contents = win_autorun_inf_contents.replace('\n', '\r\n')

        f = open(os.path.join(destdir, win_autorun_inf), 'wb')
        f.write(win_autorun_inf_contents)
        f.close()

        os.system('cp %s %s' % ('autorun-livecd/autorun-linux-script', destdir))

    def _add_other_files_installed(self,
                                   destdir):
        autorun_dir = 'VPNease'  # XXX: constants
        autorun_readme_html = 'README.htm'
        autorun_ico = 'autorun.ico'

        lnx_autorun_script = 'autorun'
        win_autorun_inf = 'Autorun.inf'
        win_autorun_inf_contents = textwrap.dedent("""\
        [autorun]
        shellexecute=%(autorun_htm)s
        icon=%(autorun_ico)s
        action=VPNease
        label=VPNease (Installed)
        """) % {'autorun_ico': '%s\\autorun.ico' % autorun_dir,
                'autorun_htm': autorun_readme_html}
        win_autorun_inf_contents = win_autorun_inf_contents.replace('\n', '\r\n')
        
        f = open(os.path.join(destdir, win_autorun_inf), 'wb')
        f.write(win_autorun_inf_contents)
        f.close()

        os.system('cp %s %s' % ('autorun-livecd/autorun-linux-script', destdir))

    def _render_pages(self):
        pages = [ (AutorunInstalledReadmePage(), 'generated/autorun-installed/README.htm'),
                  (AutorunLivecdReadmePage(), 'generated/autorun-livecd/README.htm') ]

        staticfiles = [
            'cb.css',
            'formal.css',
            'form.css',
            'hacks.css',
            'layout.css',
            'login.css',
            'print-site.css',
            'print-ui.css',
            'print-cb.css',
            'print-formal.css',
            'site.css',

            # XXX: .js files?
        
            'external.gif',
            'bg-fieldset1-top.gif',
            'bg-fieldset1-bottom.gif',
            'bg-fieldset2-top.gif',
            'bg-fieldset2-bottom.gif',
            'bg-fieldset2-bottom.gif',
            'bg-button.gif',
            'bg-button.gif',
            'bg-box.gif',
            'bg-login-1.gif',
            'bg-login-2.gif',
            'bg-main-2.gif',
            'bg-main.gif',
            'bg-main-no-nav.gif',
            'bg-header.jpg',
            'bg-nav-a.gif',
            'bg-nav-a.gif',
            'sep.gif',
            ]
        
        os.system('rm -rf generated')
        os.system('mkdir -p generated')
        os.system('mkdir -p generated/autorun-installed')
        os.system('mkdir -p generated/autorun-livecd')
        os.system('mkdir -p generated/autorun-installed/VPNease')
        os.system('mkdir -p generated/autorun-livecd/VPNease')
        
        for page, outfile in pages:
            s = page.renderSynchronously()   # result is utf8 encoded
            f = open(outfile, 'wb')
            f.write(s)
            f.close()

        for i in staticfiles:
            os.system('cp static/%s generated/autorun-installed/VPNease/' % i)
            os.system('cp static/%s generated/autorun-livecd/VPNease/' % i)

    def _prepare_zips(self):
        os.system('cd generated/autorun-installed; zip -r ../autorun-installed.zip .')
        os.system('cd generated/autorun-livecd; zip -r ../autorun-livecd.zip .')

    def generate_zipfiles(self):
        self._render_pages()
        self._add_other_files_livecd('generated/autorun-livecd')
        self._add_other_files_installed('generated/autorun-installed')
        self._prepare_zips()
        
if __name__ == '__main__':
    t = AutorunZipHelper()
    t.generate_zipfiles()
