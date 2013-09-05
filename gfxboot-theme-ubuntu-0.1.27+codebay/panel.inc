% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
%
% Panel handling.
%
% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Some global vars.
%
/panel.size     { clip.size pop 24 } def
/panel.y        { clip.size exch pop panel.size exch pop sub 10 sub } def
/panel.text.y	{ panel.y 5 add } def
/panel.font	font.normal def
/panel.normal	panel_normal_color def
/panel.high	panel_high_color def
/panel.bg	panel_bg_color def
/panel.border	panel_border_color def

/.panel.full    1 def
/.panel.short   2 def
/.panel.both    .panel.full .panel.short or def

% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Init panel.
%
% ( ) ==> ( )
%
/panel.init {

  /panel.back 0 panel.y moveto panel.size savescreen def

  % define panel layout
  /panel.template [

    % [ key x label show_func width_func update_func init_func ]

    help.getmessages "" ne {
      [ .panel.both [ keyF1 0 "F1" /panel.help /panel.help.width /panel.help.update .undef ] ]
    } if
    [ .panel.short [ keyF2 0 "F2" /panel.options /panel.options.width /panel.options.update .undef ] ]

  ] def

  % initialize all

  % Initialize stuff which was removed from the list
  bits.init
  lang.init
  keymap.init
  video.init
  access.init
  
  panel.template { 1 get 6 get dup .undef ne { exec } { pop } ifelse } forall

  /panel.full [
    panel.template {
      dup 0 get .panel.full and 0 ne { 1 get } { pop } ifelse
    } forall
  ] def

  /panel.short [
    panel.template {
      dup 0 get .panel.short and 0 ne { 1 get } { pop } ifelse
    } forall
  ] def

  /panel panel.short def

  panel.show
} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Show panel.
%
% ( ) ==> ( )
%
/panel.show {
  panel.font setfont

%  panel.bg setcolor
  0 panel.y moveto
%  currentpoint
  panel.back restorescreen
%  currenttransparency
%  50 settransparency
%  panel.size fillrect
%  settransparency
%  moveto

%  panel.border setcolor
%  0 -1 rmoveto
%  0 1 clip.size pop 3 div { pop putpixel 3 0 rmoveto } for

  % don't change xmenu
  /xmenu xmenu

  /panel.x 0 def
  panel { dup {
    dup 1 panel.x put
    dup 4 get exec over 2 get strsize pop add 20 add panel.x add /panel.x exch def
    dup 5 get exec
  } { pop } ifelse } forall

  def

} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Handle keyboard input.
%
% ( key_in ) ==> ( key_out )
%
/panel.input {
  panel { dup {
    dup 0 get 2 index eq { 3 get exec pop 0 exit } { pop } ifelse
  } { pop } ifelse } forall
} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Draw panel entry label and move to text field.
%
% ( panel ) => ( )
%
/panel.text.moveto {
  /panel.tmp.x over 1 get 10 add def
  /panel.tmp.F exch 2 get def
  
  panel.tmp.x panel.text.y moveto
  panel.high setcolor panel.tmp.F show
  panel.normal setcolor

  6 0 rmoveto
} def


