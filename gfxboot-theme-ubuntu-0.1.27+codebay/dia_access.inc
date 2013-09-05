% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
%
% Accessibility mode selector.
%
% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


/access.option .undef def

/.access.none 0 def
/.access.v1 1 def
/.access.v2 2 def
/.access.v3 3 def
/.access.m1 4 def

/access.optionnames [
  .undef
  "v1" "v2" "v3"
  "m1"
] def

% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Initialise accessibility menu.
%
% ( ) ==> ( )
%
/access.init {
  /xmenu.access .xm_size array def
  /xmenu xmenu.access def

  xmenu .xm_current .access.none put

  xmenu .xm_list [
    /txt_access_none
    /txt_access_v1 /txt_access_v2 /txt_access_v3
    /txt_access_m1
  ] put

  xmenu .xm_title /txt_access put

  pmenu.init
} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Update accessibility status.
%
% ( ) ==> ( )
%
/access.update {
  /xmenu xmenu.access def

  access.optionnames xmenu .xm_current get get dup .undef eq {
    pop
    /access.option .undef def
  } {
    dup length 7 add string /access.option exch def
    "access=%s" access.option sprintf
  } ifelse

  /window.action actRedrawPanel def

  pmenu.update
} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Show window.
%
% ( ) => ( )
%
/panel.access {
  "access" help.setcontext

  window.xmenu
  dup .xmenu xmenu.access put
  dup .xmenu.update /access.update put
  dup window.init
      window.show
} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Return width of panel entry.
%
% ( ) => ( width )
%
/panel.access.width {
  /xmenu xmenu.access def

  pmenu.width
} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Redraw panel entry.
%
% ( panel ) => ( )
%
/panel.access.update {
  /xmenu xmenu.access def

  pmenu.panel.update
} def
