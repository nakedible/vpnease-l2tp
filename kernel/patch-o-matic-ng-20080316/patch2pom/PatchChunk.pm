#!/usr/bin/perl -w
#
# PatchChunk.pm helper package for the patch2pom script
# (C) 2005      by Jonas Berlin <xkr47@outerspace.dyndns.org>
#
# This code is subject to the GNU GPLv2
#
# This package represents a chunk of a diff -Nru style file, where a
# chunk means a block starting with "@@ -1,2 +3,4 @@" and the
# lines following that belong to that block.

package PatchChunk;

use strict;

our $TYPE_NONE = 0;
our $TYPE_BOTH = 1;
our $TYPE_NEW = 2;
our $TYPE_OLD = 3;

my $NONEWLINE_STR = "\\ No newline at end of file\n";

sub typename {
    my $this = shift;
    my $type = shift;
    if($type == $TYPE_NONE) {
	return "NONE";
    } elsif($type == $TYPE_BOTH) {
	return "BOTH";
    } elsif($type == $TYPE_NEW) {
	return "NEW";
    } elsif($type == $TYPE_OLD) {
	return "OLD";
    } else {
	return "<INVALID $type>";
    }
}


sub _typechar {
    my $type = shift;
    if($type == $TYPE_NONE) {
	return "";
    } elsif($type == $TYPE_BOTH) {
	return " ";
    } elsif($type == $TYPE_NEW) {
	return "+";
    } elsif($type == $TYPE_OLD) {
	return "-";
    } else {
	return "INVALIDTYPE $type ";
    }
}

sub _warnonce {
    my $this = shift;
    my $warning = shift;

    unless($this->{_warned}->{$warning}) {
	$this->{_warned}->{$warning} = 1;
	print STDERR "\033[36;1;40mWarning: $warning\033[m\n";
    }
}

sub new {
    my $class = shift;
    $class = ref($class) || $class;
    my $this = {}; # $class->SUPER::new();
    bless $this, $class;

    my $line = shift;
    return undef unless($line =~ /^\@\@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? \@\@.*$/);

    $this->{oldstart}  = $1;
    $this->{oldlen}    = defined($2) ? $2 : 1;
    $this->{newstart}  = $3;
    $this->{newlen}    = defined($4) ? $4 : 1;

    $this->{_oldleft}  = $this->{oldlen};
    $this->{_newleft}  = $this->{newlen};

    $this->{_state}     = $TYPE_NONE;
    $this->{nonewline} = 0;
    $this->{finished}  = 0;

    $this->{_warned}    = {};

    return $this;
}

sub _finish_minichunk {
    my $this = shift;

    if($this->{_state} != $TYPE_NONE) {
	push @{$this->{minichunks}}, $this->{lines};
	push @{$this->{minichunktypes}}, $this->{_state};
    }
}

# to be used at EOF or unidentified data
sub finish {
    my $this = shift;
    return if($this->{finished});
    $this->{finished} = 1;
    $this->_finish_minichunk();
    $this->_warnonce("diff counters broken\n") if($this->{_oldleft} != 0 || $this->{_newleft} != 0);
}

sub add_line {
    my $this = shift;
    my $line = shift;

    if($this->{finished}) {
	return 0;
    }

    my $newstate;
    if($line =~ /^ /) {
	$newstate = $TYPE_BOTH;
    } elsif($line =~ /^\+/) {
	$newstate = $TYPE_NEW;
    } elsif($line =~ /^-/) {
	$newstate = $TYPE_OLD;
    } elsif($line eq $NONEWLINE_STR) {
	$this->{nonewline} = 1;
	$this->finish();
	return 1;
    } else {
	$this->finish();
	return 0;
    }

    if($newstate != $TYPE_NEW) {
	if($this->{_oldleft} <= 0) {
	    $this->{oldlen}++;
	    $this->_warnonce("diff counters broken\n");
	} else {
	    $this->{_oldleft}--;
	}
    }

    if($newstate != $TYPE_OLD) {
	if($this->{_newleft} <= 0) {
	    $this->{newlen}++;
	    $this->_warnonce("diff counters broken\n");
	} else {
	    $this->{_newleft}--;
	}
    }

    if($newstate != $this->{_state}) {
	$this->_finish_minichunk();
	$this->{lines} = [];
	$this->{_state} = $newstate;
    }

    push @{$this->{lines}}, substr($line, 1);

    return 1;
}

sub adjust_position {
    my $this = shift;
    my ($oldoff, $newoff) = @_;

    $this->{oldstart} += $oldoff;
    $this->{newstart} += $newoff;
}

sub format_minichunk {
    my $this = shift;
    my $idx = shift;

    return "<INVALID IDX $idx>" if($idx < 0 || $idx >= scalar(@{$this->{minichunks}}));
    my $char = _typechar($this->{minichunktypes}->[$idx]);
    return $char.join($char,@{$this->{minichunks}->[$idx]});
}

sub format {
    my $this = shift;
    my $str;
    $str = "@@ -".$this->{oldstart}.($this->{oldlen} != 1 ? ",".$this->{oldlen} : "");
    $str .=  " +".$this->{newstart}.($this->{newlen} != 1 ? ",".$this->{newlen} : "");
    $str .= " @@\n";
    for(my $i=0; $i<scalar(@{$this->{minichunks}}); ++$i) {
	$str .= $this->format_minichunk($i);
    }
    $str .= $NONEWLINE_STR if($this->{nonewline});
    return $str;
}

1
