#!/usr/bin/perl -w
#
# PatchFile.pm helper package for the patch2pom script
# (C) 2005      by Jonas Berlin <xkr47@outerspace.dyndns.org>
#
# This code is subject to the GNU GPLv2
#
# This package represents a single file from a diff -Nru style patch.

package PatchFile;

use strict;

my $STATE_DIFF_OR_MINUS = 0;
my $STATE_MINUS = 1;
my $STATE_PLUS = 2;
my $STATE_CHUNKS = 10;

sub new {
    my $class = shift;
    $class = ref($class) || $class;
    my $this = {}; # $class->SUPER::new();
    bless $this, $class;

    $this->{_state}   = $STATE_DIFF_OR_MINUS;
    $this->{finished} = 0;
    $this->{success}  = 0;
    $this->{started}  = 0;
    $this->{chunks}   = [];

    return $this;
}

sub _parse_fileline {
    my $line = $_[0];

    unless($line =~ /^...\s([^\t\s]+)[\t\s]*([^\t\s]*)/) {
	print STDERR "\033[36;1;40mInvalid file line:\n$line\033[m\n";
	exit(10);
    }

    return { file => $1, comments => $2 };
}

sub _finish_chunk {
    my $this = shift;

    return unless(defined($this->{_chunk}));

    $this->{_chunk}->finish();
    push @{$this->{chunks}}, $this->{_chunk};
    if($this->{_chunk}->{nonewline}) {
	$this->{finished} = 1;
	$this->{success} = 1;
    }
    $this->{_chunk} = undef;
}

# call at eof or next /^diff /
sub finish {
    my $this = shift;

    $this->_finish_chunk();
    $this->{finished} = 1;
    $this->{success} = scalar(@{$this->{chunks}}) > 0;
}

sub format {
    my $this = shift;
    my $str = $this->{diffline};
    $str .= "--- ".$this->{old}->{file}."\t".$this->{old}->{comments}."\n";
    $str .= "+++ ".$this->{new}->{file}."\t".$this->{new}->{comments}."\n";
    foreach my $chunk (@{$this->{chunks}}) {
	$str .= $chunk->format();
    }
    return $str;
}

sub add_line {
    my $this = shift;
    my $line = shift;

    return 0 if($this->{finished});

    if(/^diff /) {
	unless($this->{_state} == $STATE_DIFF_OR_MINUS) {
	    $this->finish();
	    return 0;
	}
	$this->{diffline} = $line;
	$this->{_state} = $STATE_MINUS;
	$this->{started} = 1;

    } elsif(($this->{_state} == $STATE_DIFF_OR_MINUS || $this->{_state} == $STATE_MINUS) && /^--- /) {
	$this->{old} = _parse_fileline($line);
	$this->{_state} = $STATE_PLUS;
	$this->{started} = 1;

    } elsif($this->{_state} == $STATE_PLUS && /^\+\+\+ /) {
	$this->{new} = _parse_fileline($line);
	$this->{_state} = $STATE_CHUNKS;

    } elsif($this->{_state} == $STATE_CHUNKS) {
	my $isnewchunk = $line =~ /^@@/;

	my $ret = 1;

	if(defined($this->{_chunk})) {
	    if($isnewchunk) {
		$this->{_chunk}->finish();
	    } else {
		$ret = $this->{_chunk}->add_line($line);
	    }

	    if($this->{_chunk}->{finished}) {
		$this->_finish_chunk();
	    }
	}

	if($isnewchunk && !$this->{finished}) {
	    $this->{_chunk} = new PatchChunk($_);
	    $ret = 0 unless(defined($this->{_chunk}));
	}

	if(!$ret) {
	    $this->finish();
	    return 0;
	}
    } else {
	return 0;
    }
    return 1;
}
