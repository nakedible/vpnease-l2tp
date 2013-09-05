% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
%
% Panel d-i mode selector.
%
% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


/dimode.option .undef def

/.dimode.normal 0 def
/.dimode.expert 1 def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Initialise d-i mode menu.
%
% ( ) ==> ( )
%
/dimode.init {
  /xmenu.dimode .xm_size array def
  /xmenu xmenu.dimode def

  xmenu .xm_current .dimode.normal put

  xmenu .xm_list [ /txt_normal_mode /txt_expert_mode ] put

  pmenu.init
} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Update d-i mode status.
%
% ( ) ==> ( )
%
/dimode.update {
  /xmenu xmenu.dimode def

  xmenu .xm_current get .dimode.normal eq {
    /dimode.option .undef def
  } {
    /dimode.option "DEBCONF_PRIORITY=low" def
  } ifelse

  /window.action actRedrawPanel def

  pmenu.update
} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Show window.
%
% ( ) => ( )
%
/panel.dimode {
  "dimode" help.setcontext

  window.xmenu
  dup .xmenu xmenu.dimode put
  dup .xmenu.update /dimode.update put
  dup window.init
      window.show
} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Return width of panel entry.
%
% ( ) => ( width )
%
/panel.dimode.width {
  /xmenu xmenu.dimode def

  pmenu.width
} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Redraw panel entry.
%
% ( panel ) => ( )
%
/panel.dimode.update {
  /xmenu xmenu.dimode def

  pmenu.panel.update
} def
