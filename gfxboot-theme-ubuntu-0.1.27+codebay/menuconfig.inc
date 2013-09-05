% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
%
% Read syslinux configuration to get human-readable names for menu items, and
% to decide whether to hide menu items. The configuration used is the same as
% that used by the syslinux simple menu system, so you can use the same
% configuration file for both.
%
% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

/menuconfig.find {
  [
    "/syslinux.cfg"
    "/isolinux.cfg"
    "/isolinux/isolinux.cfg"
    "/boot/isolinux/isolinux.cfg"
  ] {
    dup filesize .undef ne { findfile return } if
    pop
  } forall
  .undef
} def

% Duplicate len bytes of string.
% ( string len -- string )
/strndup {
  /strndup.len exch def
  /strndup.src exch cvp def
  /strndup.dst strndup.len string cvp def
  strndup.dst strndup.src strndup.len memcpy
  strndup.dst strndup.len 0 put
  strndup.dst cvs
} def

% Force to lower case. Overwrites string.
% ( string -- string )
/tolower {
  dup length 0 eq { return } if
  dup length 1 sub 0 1 rot {
    over over get 32 or 2 index 3 1 roll put
  } for
} def

% Skip whitespace. Advances string.
% ( string -- string )
/menuconfig.skipspace {
  {
    dup 0 get
    dup 0 eq exch ' ' gt or { exit } if
    1 add
  } loop
} def

% Find the next word boundary (NUL or whitespace).
% ( string -- pos )
/menuconfig.nextspace {
  0 {
    over over get
    dup 0 eq exch ' ' le or { exit } if
    1 add
  } loop
  exch pop
} def

% Extract a keyword (always forced to lowercase). keyword_str must be freed.
% ( config_str -- trailing_str keyword_str )
/menuconfig.keyword {
  dup menuconfig.nextspace
  over over add               % get trailing string
  3 1 roll strndup tolower    % get lowercase keyword string
} def

% Extract a word. word_str must be freed.
% ( config_str -- trailing_str word_str )
/menuconfig.word {
  dup menuconfig.nextspace
  over over add               % get trailing string
  3 1 roll strndup            % get word string
} def

% Interpret a string as a number and return it, or .undef on failure.
% Only supports hexadecimal numbers (optionally preceded by "0x").
% ( string -- number )
/menuconfig.strtol {
  tolower
  dup 0 get '0' eq over 1 get 'x' eq and { 2 add } if
  /menuconfig.strtol.tmp 0 def
  {
    dup '0' ge over '9' le and {
      '0' sub menuconfig.strtol.tmp 16 mul add
      /menuconfig.strtol.tmp exch def
    } {
      dup 'a' ge over 'f' le and {
        'a' sub 10 add menuconfig.strtol.tmp 16 mul add
        /menuconfig.strtol.tmp exch def
      } {
        pop .undef return
      } ifelse
    } ifelse
  } forall
  menuconfig.strtol.tmp
} def

% Set the human-readable text for the current menu item.
% ( string -- )
/menuconfig.sethuman {
  menuconfig.curlabel .undef eq { pop return } if

  /menuconfig.human exch def

  /menuconfig.idx 0 def
  menuconfig.entries {
    menuconfig.curlabel eq {
      menuconfig.humans menuconfig.idx menuconfig.human put
      return
    } if
    /menuconfig.idx inc
  } forall
} def

% Remove the current menu item from the menu.
% ( -- )
/menuconfig.hidelabel {
  menuconfig.curlabel .undef eq { return } if

  /menuconfig.idx 0 def
  menuconfig.entries {
    menuconfig.curlabel eq {
      % Copy everything up to here into new arrays.
      /menuconfig.newargs menuconfig.args length 1 sub array def
      /menuconfig.newentries menuconfig.entries length 1 sub array def
      /menuconfig.newhumans menuconfig.humans length 1 sub array def
      menuconfig.idx 0 ne {
        0 1 menuconfig.idx 1 sub {
          menuconfig.args over get
          menuconfig.newargs 2 index rot put
          menuconfig.entries over get
          menuconfig.newentries 2 index rot put
          menuconfig.humans over get
          menuconfig.newhumans 3 1 roll put
        } for
      } if

      % Slide everything else down one place.
      menuconfig.idx 1 menuconfig.entries length 2 sub {
        menuconfig.args over 1 add get
        menuconfig.newargs 2 index rot put
        menuconfig.entries over 1 add get
        menuconfig.newentries 2 index rot put
        menuconfig.humans over 1 add get
        menuconfig.newhumans 3 1 roll put
      } for

      /menuconfig.args menuconfig.newargs def
      /menuconfig.entries menuconfig.newentries def
      /menuconfig.humans menuconfig.newhumans def

      return
    } if
    /menuconfig.idx inc
  } forall
} def

% ( menu_entries_array menu_args_array -- menu_humans_array menu_entries_array menu_args_array )
% The returned menu_args_array (kernel parameters), menu_entries_array
% (identifiers), and menu_humans_array (human-readable names) will have any
% hidden entries removed.
/menuconfig.init {
  dup length array /menuconfig.args exch def
  over length array /menuconfig.entries exch def
  over length array /menuconfig.humans exch def

  % copy input arrays; initialise menuconfig.humans
  /menuconfig.idx 0 def
  {
    menuconfig.args menuconfig.idx rot put
    /menuconfig.idx inc
  } forall
  /menuconfig.idx 0 def
  {
    dup menuconfig.entries menuconfig.idx rot put
    menuconfig.humans menuconfig.idx rot put
    /menuconfig.idx inc
  } forall

  % we only understand syslinux configuration
  syslinux not {
    menuconfig.humans menuconfig.entries menuconfig.args return
  } if

  % load configuration file; return if not found
  menuconfig.find dup .undef eq {
    menuconfig.humans menuconfig.entries menuconfig.args return
  } if
  /menuconfig.file exch cvs def

  /menuconfig.curlabel .undef def

  menuconfig.file {
    % skip over any NULs we've left behind; exit if there's really no more
    % memory left to go
    {
      dup cvp length 0 eq { exit } if
      dup 0 get 0 ne { exit } if
      1 add
    } loop
    dup cvp length 0 eq { exit } if

    % break lines at \r or \n
    dup "\x0d" strstr dup 0 ne { 1 sub over exch 0 put } { pop } ifelse
    dup "\n" strstr dup 0 ne { 1 sub over exch 0 put } { pop } ifelse

    menuconfig.skipspace menuconfig.keyword
    dup "gfxboot-foreground" eq {
      over menuconfig.skipspace menuconfig.strtol dup .undef ne {
        /menu.text.select over def
        /boot.text.options over def
        /boot.text.normal over def
        /panel.high exch def
      } { pop } ifelse
    } if
    dup "gfxboot-background" eq {
      over menuconfig.skipspace menuconfig.strtol dup .undef ne {
        /menu.text.normal over def
        /panel.normal exch def
      } { pop } ifelse
    } if
    dup "label" eq {
      over menuconfig.skipspace strdup /menuconfig.curlabel exch def
    } if
    dup "menu" eq {
      over menuconfig.skipspace menuconfig.keyword
      dup "label" eq { over menuconfig.skipspace strdup menuconfig.sethuman } if
      dup "hide" eq { menuconfig.hidelabel } if
      free rot pop exch
    } if
    free

    % skip to end of line
    dup length add
  } loop pop
  menuconfig.file free

  menuconfig.humans menuconfig.entries menuconfig.args
} def
