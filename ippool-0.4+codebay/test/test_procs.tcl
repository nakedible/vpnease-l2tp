# -*- tcl -*-

if {[lsearch [namespace children] ::tcltest] == -1} {
    package require tcltest
    namespace import -force ::tcltest::*
}

set message ""

proc clearResult { } {
    global message
    set message ""
}

proc ippoolConfig { args } {
    global message
    catch { exec ../ippoolconfig $args } msg
    set message $message\n$msg
    return $message\n
}

proc sleep { args } {
    global message
    exec sleep $args
    return $message
}

proc addCrLf { args } {
    global message
    set message $message\n
    return $message
}

# Use cat -E to put a '$' on the end of each line. This means lines
# ending with a '\' won't be joined in the output.

proc catFile { args } {
    global message
    catch { exec cat -E $args } msg
    set message $message\n$msg
    return $message\n
}


