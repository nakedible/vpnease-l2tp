% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
%
% Handle translations.
%
% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Set language.
%
% ( locale ) ==> ( true|false )
%
/setlang {
  config.lang over eq { pop false return } if

  /config.lang exch def

  /help.messages .undef def

  texts.msgstr {
    texts.msgstr dup { free } forall free
    /texts.msgstr .undef def
  } if

  findtexts

  true
} def



% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Set keyboard map.
%
% ( locale ) ==> ( )
%
/setkeymap {
  config.keymap.locale over eq { pop false return } if

  /config.keymap.locale exch def

  /setkeymap.found false def
  keymaps {
    dup .km.locales get {
      config.keymap.locale eq {
        dup /config.keymap exch def /setkeymap.found true def exit
      } if
    } forall
    pop
    setkeymap.found { exit } if
  } forall

  % if we couldn't find anything, try without the country
  setkeymap.found not {
    config.keymap.locale "_" strstr dup 0 ne {
      1 sub
      dup string /lang.tmp exch def
      lang.tmp cvp config.keymap.locale cvp 2 index memcpy
      lang.tmp exch 0 put
      keymaps {
        dup .km.locales get {
          lang.tmp eq {
            dup /config.keymap exch def /setkeymap.found true def exit
          } if
        } forall
        pop
        setkeymap.found { exit } if
      } forall
    } {
      pop
    } ifelse
  } if

} def



% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Find texts for current language.
%
% ( ) ==> ( )
%
/findtexts {
  texts.file free /texts.file .undef def
  16 string dup config.lang "%s.tr" 2 index sprintf findfile exch free
  dup .undef eq {
    config.lang length 2 gt {
      pop 16 string
      dup config.lang 1 get config.lang 0 get "%c%c.tr" 3 index sprintf findfile exch free
      dup {
        /config.lang 2 string
          config.lang 1 get config.lang 0 get "%c%c" 3 index sprintf
        def
      } if
    } if
  } if
  dup .undef eq { pop "en.tr" findfile } if
  /texts.file over def
  dup .undef eq { pop 0 cvp } if
  cvs
  /ft.len over cvp length def
  /ft.str exch def
  /ft.pos 0 def

  texts {
    ft.pos ft.str length add ft.len lt {
      ft.str def
      /ft.str ft.str dup length 1 add /ft.pos over ft.pos add def add def
    } {
      "No Texts!" def
    } ifelse
  } forall
} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Translate menu entry.
%
% ( text ) ==> ( text )
%
/translate {
  translations.init

  texts.msgid .undef eq texts.msgstr .undef eq or { return } if

  0 1 texts.msgid length 1 sub {
    texts.msgid over get 2 index eq {
      texts.msgstr over get exch pop exit
    } { pop } ifelse
  } for
} def


% - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
% Read menu translations.
%
% ( ) ==> ( )
%
/translations.init {
  texts.msgstr { return } if

  texts.msgid .undef eq {
    /config.lang.tmp config.lang def
    /config.lang "en" def
    findtexts
    /texts.msgid [ texts { exec strdup } forall ] def
    /config.lang config.lang.tmp def
  } if
  findtexts
  /texts.msgstr [ texts { exec strdup } forall ] def
} def

