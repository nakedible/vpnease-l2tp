#!/usr/bin/perl
#
# Netfilter_POM.pm, part of the patch-o-matic 'next generation' package
# (C) 2003-2004 by Harald Welte <laforge@netfilter.org>
# (C) 2004	by Jozsef Kadlecsik <kadlec@blackhole.kfki.hu>
#
# This code is subject to the GNU GPLv2
#
# $Id: Netfilter_POM.pm 6736 2007-01-12 17:07:08Z /C=DE/ST=Berlin/L=Berlin/O=Netfilter Project/OU=Development/CN=kaber/emailAddress=kaber@netfilter.org $
#
# The idea is to have the backend seperated from the frontend.  Thus,
# other frontends (like ncurses,...) could potentially be implemented on
# top of this.
#
package Netfilter_POM;

# we could export the public functions into caller namespace 
#require Exporter;
#BEGIN {
#	@ISA = qw(Exporter);
#}
#@EXPORT = qw();

use strict;
use Carp;
use File::Temp;
use File::Copy;
use File::Path;
use File::Basename;
#use Data::Dumper;

my $BIN_PATCH = "patch";

# print the last error messages
#
sub perror {
	my $self = shift;

	if ($self->{ERRMSG}) {
		print STDERR $self->{ERRMSG};
		$self->{ERRMSG} = '';
	}
}

# count the number of hunks in a unified diff file
#
sub count_hunks {
	my($file) = @_;
	my($hunk_count);

	open(INFILE, $file) || return -1;
	while (my $line = <INFILE>) {
		chomp($line);
		if ($line =~ /^@@/) {
			$hunk_count++;
		}
	}
	close(INFILE);

	return $hunk_count;
}

# copy patch files from the source tree, collecting
# file names from the unified diff file
#
sub copy_patchfiles {
	my $self = shift;
	my($file, $copy, $proj) = @_;
	my @files;

	open(INFILE, $file)
		or croak "Cannot open patch file $file: $!";
	while (my $line = <INFILE>) {
		chomp($line);
		if ($line =~ /^\+\+\+ (\S+)/) {
			push(@files, $1);
		}
	}
	close(INFILE);
	foreach $file (@files) {
		# patch can be applied by 'patch -p1'
		$file =~ s,[^/]+/,,;
		my $srcfile = "$self->{projects}->{$proj}->{PATH}/$file";
		my $destfile = "$copy/$file";
		my $destdir = File::Basename::dirname($destfile);
		if (!-d $destdir) {
			if (!File::Path::mkpath($destdir)) {
				$self->{ERRMSG} .= "unable to mkpath($destdir) while copying patchfiles: $!\n";
				return 0;
			}
		}
		# Don't copy existing files and ignore errors
		# (there can be new files in patches (but shouldn't!)
		File::Copy::copy($srcfile, $destfile) unless -f $destfile;
	}
	return 1;
}

# get the kernel version of a specified kernel tree
#
sub linuxversion {
	my $self = shift;
	my($version, $patchlevel, $sublevel);

	open(MAKEFILE, "$self->{projects}->{linux}->{PATH}/Makefile")
		or croak "No kernel Makefile in $self->{projects}->{linux}->{PATH}!";
	while (my $line = <MAKEFILE>) {
		chomp($line);
		if ($line =~ /^VERSION =\s*(\S+)/) {
			$version = $1;
		} elsif ($line =~ /^PATCHLEVEL =\s*(\S+)/) {
			$patchlevel = $1;
		} elsif ($line =~ /^SUBLEVEL =\s*(\S+)/) {
			$sublevel = $1;
		}
	}
	close(MAKEFILE);
	$self->{projects}->{linux}->{VERSION} = join('.', $version, $patchlevel, $sublevel);
}

# get the iptables version of a specified source tree
#
sub iptablesversion {
	my $self = shift;
	my($version);

	open(MAKEFILE, "$self->{projects}->{iptables}->{PATH}/Makefile")
		or croak "Missing Makefile from $self->{projects}->{iptables}->{PATH}!";
	while (my $line = <MAKEFILE>) {
		chomp($line);
		if ($line =~ /^IPTABLES_VERSION:=(\S+)/) {
			$version = $1;
			# don't support versioning like 1.2.3b!
			$version =~ s/[^\d\.]//g;
			close(MAKEFILE);
			$self->{projects}->{iptables}->{VERSION} = $version;
			return;
		}
	}
	close(MAKEFILE);
	croak "Makefile in $self->{projects}->{iptables}->{PATH} does not contain iptables version!";
}

# Check existence of elements in a patchlet 
# without springing into existence the checked elements
sub safe_exists {
	my $patchlet = shift;
	my @elements = @_;

	my $href = $patchlet;
	foreach (@elements) {
		return 0 unless exists($href->{$_}) && $href->{$_};
		$href = $href->{$_};
	}
	return 1;
}

# this should be taken from RPM or something like that
# first argument is the project we want to patch
# second argument is the operator
# third argument is the version of the patch we want to apply
#
sub version_compare {
	my $self = shift;
	my($proj, $op, $ver2) = @_;
	my($ver1, @ver1, @ver2, $sv, $res);
	my(@weight) = (10000, 100, 1);

	@ver1 = split(/\./, $self->{projects}->{$proj}->{VERSION});
	@ver2 = split(/\./, $ver2);

	$ver1 = $ver2 = 0;
	foreach $sv (0..$#ver2) {
		$ver1 += $ver1[$sv] * $weight[$sv];
		$ver2 += $ver2[$sv] * $weight[$sv];
	}
	eval "\$res = $ver1 $op $ver2";
	# We return the numeric version of the patch
	# for requirements_fulfilled below 
	return ($res ? $ver2 : 0);
}

# are the info file requirements for a specific patchlet fulfilled?
#
sub info_reqs_fulfilled {
	my $self = shift;
	my($patchlet, $proj, $version) = @_;

	# Project version we want to patch must fulfil the version 
	# requirements of a given patchlet
	my $pver = $proj;
	$pver .= '-' . $version if $version;
	foreach my $req (@{$patchlet->{info}->{requires}}) {
		my ($prog, $op, $ver) = $req =~/(\S+)\s*(==|>=|>|<=|<)\s*(\S+)/;

		# if the requirement refers to the tested patchlet,
		# project version must fulfil the requirement.
		# Multiple requirements are ANDed.
		return 0 if $pver eq $prog 
			    && !$self->version_compare($proj, $op, $ver);
	}
	return 1;
}

# are the requirements for a specific patchlet fulfilled?
#
sub requirements_fulfilled {
	my $self = shift;
	my $patchlet = shift;
	my($type, $proj, $ver, $bingo, $match);
	my $best_match = 0;

	# Search best (nearest) match
	foreach $type (qw(patch files ladds)) {
		next unless exists $patchlet->{$type};
		foreach $proj (keys %{$patchlet->{$type}}) {
			$bingo = 0;
			foreach $ver (keys %{$patchlet->{$type}->{$proj}}) {
				# No version has got the lowest possible match value
				$match = !$ver ? 1
					: $ver =~ /$self->{projects}->{$proj}->{branch}/
					  && $self->version_compare($proj, '>=', $ver);
				next if $bingo >= $match
					|| !$self->info_reqs_fulfilled($patchlet, $proj, $ver);
				$bingo = $match;
				$patchlet->{$type}->{$proj}->{best} =
					$patchlet->{$type}->{$proj}->{$ver};
				$best_match = 1;
			}
			if ($bingo == 0) {
				delete $patchlet->{$type}->{$proj};
			}
		}
	}
FOUND:	
	#print Dumper($patchlet);
	if ($best_match) {
		return 1;
	} else {
		$self->{ERRMSG} .= "$patchlet->{name} does not match your source trees, skipping...\n";
		return 0;
	}
}

# recursively test if all dependencies are fulfilled
# 
# return values:
# 	 1	dependencies fulfilled
# 	 0	dependencies not fulfilled
# 	-1	dependencies cannot be fulfilled [conflicting patchlets]
#
sub dependencies_fulfilled {
	my $self = shift;
	my $patchlet = shift;
	my $plname = $patchlet->{name};

	for my $depend (@{$patchlet->{info}->{depends}}) {
		# Dance around references!
		my($inverse, $dep) = $depend =~ /^(!)?(.*)/;

		if (!defined($self->{patchlets}->{$dep})) {
			$self->{ERRMSG} .= "$plname has dependency on $dep, but $dep is not known\n";
			return 0;
		}
		my $applied = grep($_ eq $dep, @{$self->{applied}});
		if ($inverse && $applied) {
			$self->{ERRMSG} .= "present '$dep' conflicts with to-be-installed '$plname'\n";
			return -1;
		} elsif ($applied || $inverse) {
			# patch can be applied if all its dependecies had been applied
			# Don't check the dependecies of conflicting patches
			next;
		}
		my $ret = $self->dependencies_fulfilled($self->{patchlets}->{$dep});
		return $ret if $ret <= 0;
		if (!$self->apply_patchlet($self->{patchlets}->{$dep}, !$inverse, 1)) {
			if (!$inverse) {
				$self->{ERRMSG} .= "$dep not applied\n";
				return 0;
			} else {
				$self->{ERRMSG} .= "present '$dep' conflicts with to-be-installed '$plname'\n";
				return -1;
			}
		}
	}
	return 1;
}

sub apply_dependency {
	my $self = shift;
	my($plname, $force, $test, $copy) = @_;

	return 1 if grep($_ eq $plname, @{$self->{applied}});

	if (!$force) {
		# first test, then apply
		if (!$self->apply_patchlet($self->{patchlets}->{$plname}, 0, 1, $copy)) {
			# test failed, maybe it's already applied? Check by testing to reverse it
			if (!$self->apply_patchlet($self->{patchlets}->{$plname}, 1, 1, $copy)) {
				$self->{ERRMSG} .= "apply_dependency: unable to apply dependent $plname\n";
				return 0;
			} else {
				# apparently it was already applied, add it to list of applied patches
				push(@{$self->{applied}}, $plname);
				return 1;
			}
		} 
	}
	if (!$test) {
		if (!$self->apply_patchlet($self->{patchlets}->{$plname}, 0, 0, $copy)) {
			$self->{ERRMSG} .= "apply_dependency: unable to apply dependent $plname\n";
			return 0;
		} else {
			push(@{$self->{applied}}, $plname);
			print("apply_dependency: successfully applied $plname\n") unless $copy;
		}
	}
	return 1;
}

# apply_dependencies - recursively apply all dependencies
# patchlet: patchlet subject to recursive dependency resolving
# force: forcibly try to apply dependent patches (to see .rej's)
# test: just test wether patch could be applied
sub apply_dependencies {
	my $self = shift;
	my($patchlet, $force, $test, $copy) = @_;
	my $plname = $patchlet->{name};

	for my $dep (@{$patchlet->{info}->{depends}}) {
		# don't revert existing patches
		next if $dep =~ /^!/;

		if (!defined($self->{patchlets}->{$dep})) {
			$self->{ERRMSG} .= "$plname has dependency on $dep, but $dep is not known\n";
			return 0;
		}

		# We have to call requirements_fulfilled because
		# patches can be specified on commandline too.
		# However, there can be different dependencies in
		# different branches, so skip unmet dependencies!
		if ($self->requirements_fulfilled($self->{patchlets}->{$dep})) {
			return 0 unless	 $self->apply_dependencies($self->{patchlets}->{$dep}, 
								   $force, $test, $copy)
					 && $self->apply_dependency($dep, $force, $test, $copy);
		}
	}

	return 1;
}

# recurse through subdirectories, pushing all filenames into 
# the correspondig ladds|files->project->version array by
# differentiating between whole new files and line-adds (ladds)
#
sub recurse {
	my $self = shift;
	my($pdir, $dir, $patchlet, $proj, $ver) = @_;

	opendir(DIR, $dir)
		or croak "can't open directory $dir: $!";
	# Don't miss .foo-test files!
	my @dents = sort grep {!/^(\.\.?|CVS|\.svn|.*~)$/} readdir(DIR);
	closedir(DIR);
	foreach my $dent (@dents) {
		my $fullpath = "$dir/$dent";
		if (-f $fullpath) {
			my $key = ($dent =~ /\.ladd/ ? 'ladds' : 'files');
			push(@{$patchlet->{$key}->{$proj}->{$ver}}, "$pdir/$fullpath");
		} elsif (-d _) {
			$self->recurse($pdir, $fullpath, $patchlet, $proj, $ver);
		}
	}
}

# parse info file associated with patchlet
#
sub parse_patch_info {
	my $self = shift;
	my($info, $patchlet) = @_;
	my($help, $list);

	($patchlet->{info}->{file} = $info) =~ s,.*/,,;

	open(INFILE, $info)
		or croak "unable to open $info: $!";
	while (my $line = <INFILE>) {
		chomp($line);
		if ($help) {
			$patchlet->{info}->{help} .= $line . "\n";
		} elsif ($line =~ /^Title:\s+(.*)/) {
			$patchlet->{info}->{title} = $1;
		} elsif ($line =~ /^Author:\s+(.*)/) {
			$patchlet->{info}->{author} = $1;
		} elsif ($line =~ /^Status:\s+(.*)/) {
			$patchlet->{info}->{status} = $1;
		} elsif ($line =~ /^Repository:\s+(.*)/) {
			$patchlet->{info}->{repository} = $1;
		} elsif ($line =~ /^Requires:\s+(.*)\s*/) {
			push(@{$patchlet->{info}->{requires}}, $1);
		} elsif ($line =~ /^Depends:\s+(.*)\s*/) {
			($list = $1) =~ tr/,/ /;
			push(@{$patchlet->{info}->{depends}}, split(/\s+/, $list));
		} elsif ($line =~ /^Recompile:\s+(.*)\s*/) {
			($list = $1) =~ tr/,/ /;
			push(@{$patchlet->{info}->{recompile}}, split(/\s+/, $list));
		} elsif ($line =~ /^Successor:\s+(\S+)/) {
			$patchlet->{info}->{successor} = $1;
		} elsif ($line =~ /^Version:\s+(.*)/) {
			$patchlet->{info}->{version} = $1;
		} elsif ($line =~ /^\s*$/) {
			$help = 1;
		} else {
			close(INFILE);
			croak "unknown config key '$line' in $info";
		}
	}
	close(INFILE);

	croak "missing repository definition from $info!"
		unless defined($patchlet->{info}->{repository});

	# Backward compatibility
	return if defined $patchlet->{info}->{help};

	$info =~ s/info$/help/;
	open(INFILE, $info) or return;
	while (<INFILE>) {
		$patchlet->{info}->{help} .= $_;
	}
	close(INFILE);
	
}

# Parse a single patchlet specified as parameter.
# The collected info is stored in a hash reference
# with the structure below. If you change the structure,
# make notes here!
#
# patchlet = {
#    # basedir relative to POM dir
#    basedir	=> dirname,	
#    # filenames are relative to basedir
#    # leading 'subdir/./' must be taken into account
#    # for files from subdirectories (files and ladds)
#    name	=> patchname,	# dirname without trailing '/'
#    info	=> {
#	file	=> filename,
#	title	=> title,
#	author	=> author,
#	status	=> status,
#	repository => repository,
#	requires   => [ requirement ],
#	depends	   => [ dependency ],
#	recompile  => [ recompile ],
#	successor  => patchname
#	version	=> patchlet version
#	help	=> txt,
#    },
#    patch	=>  {
#	project => {
#	    version => [ filename ],
#	},
#    },
#    files	=> {
#	project => {
#	    version => [ filename ],
#	},
#    },
#    ladds	=> {
#	project => {
#	    version => [ filename ],
#	},
#    },
# }
sub parse_patchlet {
	my $self = shift;
	my $patchdir = shift;
	my $patchlet;

	$patchlet->{basedir} = $patchdir;
	($patchlet->{name} = $patchdir) =~ s,\./,,;
	# parse our info file
	$self->parse_patch_info($patchdir . '/info', $patchlet);

	# get list of source files that we'd need to copy
	opendir(PDIR, $patchdir)
		or croak "unable to open patchdir $patchdir: $!";
	my @dents = sort grep {!/^(\.\.?|CVS|\.svn|.*~)$/} readdir(PDIR);
	closedir(PDIR);

	foreach my $pf (@dents) {
		my $proj;
		my $ver;
		my $oldpwd;


		if ($pf =~ /\.patch/) {
			# Patch file of a project:
			# project[-ver[.plev[.sublev]]].patch[_num]
			$pf =~ /((-([\d\.]+))?\.patch(_\d+.*)?)$/;
			$ver = $3;
			($proj = $pf) =~ s/$1//;
			push(@{$patchlet->{patch}->{$proj}->{$ver}}, $pf);
		} elsif (-d "$patchdir/$pf") {
			# Project directory for ladd and whole files:
			# project[-ver[.plev[.sublev]]]		
			$pf =~ /(-([\d\.]*))?$/;
			$ver = $2;
			($proj = $pf) =~ s/$1//;
			my $oldpwd = `pwd`;
			chomp($oldpwd);
			chdir("$patchdir/$pf");
			$self->recurse($pf, '.', $patchlet, $proj, $ver);
			chdir($oldpwd);
		}
	}

	#print Dumper $patchlet;
	print '.';
	return $patchlet;
}

# parse a single update patch specified as parameter
#
sub parse_update {
	my $self = shift;
	my $pfile = shift;
	my $patchlet;
	my($project, $version, $txt);

	$patchlet->{basedir} = File::Basename::dirname($pfile);
	($patchlet->{name} = $pfile) =~ s,.*/,,;
	# parse our info file
	$self->parse_patch_info($pfile . '.info', $patchlet);

	# n_proj[-ver[.plev[.sublev]]][txt].patch
	$patchlet->{name} =~ /^\d+_(.*?)(-([\d\.]+))(.*)\.patch$/;
	($project, $version, $txt) = ($1, $3, $4);
	if (!$txt) {
		# Incremental patch: correct version number
		$version =~ s/(\d+)$/$1-1/e;
	} 
	$patchlet->{patch}->{$project}->{$version} = [ $patchlet->{name} ];

	# print Dumper $patchlet;
	print '.';
	return $patchlet;
}

# apply an old-style lineadd file
#
sub apply_lineadd {
	my $self = shift;
	my($patchlet, $laddfile, $fname, $revert, $test) = @_;
	my @newlines;
	my $kconfigmode;
	my $configmode;
	my $lookingfor;

	if (!open(LADD, $laddfile)) {
		$self->{ERRMSG} .= "unable to open ladd $laddfile\n";
		return 0;
	}

	my ($srcfile, $extn) = $fname =~ /(.*?)(\.ladd(_\d+.*)?)?$/;

	if ($srcfile =~ /Kconfig$/) {
		$kconfigmode = 1;
		$lookingfor = $revert ? <LADD> : "endmenu\n";
	} elsif ($srcfile =~ /Configure\.help/) {
		$configmode = 1;
		$lookingfor = <LADD>;
	} else {
		$lookingfor = <LADD>;
	}

	if (!open(SRC, $srcfile)) {
		close(LADD);
		$self->{ERRMSG} .= "unable to open ladd src $srcfile\n";
		return 0;
	}

	my $found = 0;
	SRCLINE: while (my $line = <SRC>) {
		push(@newlines, $line);
		if ($line eq $lookingfor) {
			$found = 1;
			if ($revert == 0) {
				my ($prev, $next, $last);
				if ($kconfigmode) {
					$prev = pop(@newlines);
				} elsif ($configmode) {
					while (($line = <SRC>) !~ /^\S/) {
						push(@newlines, $line);
					}
					$next = $line;
				}
				while (my $newline = <LADD>) {
					push(@newlines, $newline);
					$last = $newline;
				}
				# ugly kconfig/configure.help hacks
				if ($kconfigmode) {
					push(@newlines, "\n");
					push(@newlines, $prev);
				} elsif ($configmode) {
					push(@newlines, "\n")
						unless $last =~ /^\s*$/;
					push(@newlines, $next);
				}
				# append rest of sourcefile
				while ($line = <SRC>) {
					push(@newlines, $line);
				}
			} else {
				pop(@newlines) if $kconfigmode;
				while (my $newline = <LADD>) {
					my $srcline = <SRC>;
					if ($newline ne $srcline) {
						$found = -1;
						last SRCLINE;
					}
				}
			}
		}
	}
	close(LADD);
	close(SRC);
		
	if ($found == 0) {
		$self->{ERRMSG} .= "unable to find ladd slot in src $srcfile ($laddfile)\n";
		return 0;
	} elsif (!$test && $found == -1) {
		$self->{ERRMSG} .= "unable to find all to-be-removed lines in $srcfile\n";
		return 0;
	}

	if ($test == 0) {
		my $newfile = "${srcfile}.$$";
		if (!open(SRC, ">${newfile}")) {
			$self->{ERRMSG} .= "unable to write to file ${newfile}\n";
			return 0;
		}
		foreach my $line (@newlines) {
			print(SRC $line);
		}
		close(SRC);
		if (!rename($newfile, $srcfile)) {
			$self->{ERRMSG} .= "unable to replace file $srcfile\n";
			return 0;
		}
	}

	return 1;
}

sub apply_newfiles {
	my $self = shift;
	my($patchlet, $proj, $revert, $test, $copy) = @_;
	my($projpath, $file, $srcfile, $dir, $destdir, $destfile);
	my $test_found;
	my $test_notfound;

	return 1 unless safe_exists($patchlet, ('files', $proj, 'best'));

	$projpath = $copy || $self->{projects}->{$proj}->{PATH};
	for my $file (@{$patchlet->{files}->{$proj}->{best}}) {
		$srcfile = "$patchlet->{basedir}/$file";
		# project/./
		($dir = File::Basename::dirname($file)) =~ s,([^/]+/){2},,;
		$destdir = "$projpath/$dir";
		$destfile = $destdir . '/' . File::Basename::basename($file);
		if (!$test) {
			if (!$revert) {
				if (!-d $destdir) {
					if (!File::Path::mkpath($destdir)) {
						$self->{ERRMSG} .= "unable to mkpath($destdir) while applying newfile: $!\n";
						return 0;
					}
				}
				if (!File::Copy::copy($srcfile, $destfile)) {
					$self->{ERRMSG} .= "unable to copy $srcfile to $destfile: $!\n";
					return 0;
				}
				# .foo-test is executable
				chmod((stat($srcfile))[2] & 07777, $destfile);
			} else {
				if (!unlink($destfile)) {
					$self->{ERRMSG} .= "unable to remove $destfile while reverting newfile: $!\n";
					return 0;
				}
			}
		} else {
			# check if the file exists in the real directory, not the copy, it doesn't contain all files.
			$destfile = $self->{projects}->{$proj}->{PATH} . "/$dir/" . File::Basename::basename($file);
			if (-f $destfile) {
				$test_found++;
			} else {
				$test_notfound++;
			}
		}
	}

	if ($test) {
		if (!$revert && $test_found) {
			$self->{ERRMSG} .= "newfile: $test_found files in our way, unable to apply\n";
			return 0;
		} elsif ($revert && $test_notfound) {
			$self->{ERRMSG} .= "newfile: $test_notfound files missing, unable to revert\n";
			return 0;
		}
	}
		
	return 1;
}

sub apply_lineadds {
	my $self = shift;
	my($patchlet, $proj, $revert, $test, $copy) = @_;
	my($projpath, $file, $target, $copyfile);

	return 1 unless safe_exists($patchlet, ('ladds', $proj, 'best'));

	# print Dumper $patchlet;
	# apply the line-adds
	$projpath = $copy || $self->{projects}->{$proj}->{PATH};
	for $file (@{$patchlet->{ladds}->{$proj}->{best}}) {
		my $basename = File::Basename::basename($file);
		if ($proj eq 'linux') {
			if ($self->{projects}->{$proj}->{VERSION} =~ /^2\.4\.\d+/
			    && $basename =~ /^Kconfig\.ladd/) {
			    	next;
			}
			if ($self->{projects}->{$proj}->{VERSION} =~ /^2\.6\.\d+/
			    && ($basename =~ /^Config\.in\.ladd/
			        || $basename =~ /^Configure\.help/)) {
			    	next;
			}
		}
		# project/./
		($target = $file) =~ s,([^/]+/){2},,;
		($copyfile = $target) =~ s/\.ladd.*//;
		if ($copy && ! -f "$projpath/$copyfile") {
			my $destdir = File::Basename::dirname("$projpath/$copyfile");
			if (!-d $destdir) {
				if (!File::Path::mkpath($destdir)) {
					$self->{ERRMSG} .= "unable to mkpath($destdir) while testing lineadds: $!\n";
					return 0;
				}
			}
			if (!File::Copy::copy("$self->{projects}->{$proj}->{PATH}/$copyfile", "$projpath/$copyfile")) {
				$self->{ERRMSG} .= "unable to copy $self->{projects}->{$proj}->{PATH}/$copyfile while testing lineadds: $!\n";
				return 0;
			}
		}
		return 0 unless $self->apply_lineadd($patchlet, 
						     $patchlet->{basedir}.'/'.$file,
						     $projpath.'/'.$target, 
						     $revert,
						     $test);
	}

	return 1;
}

sub apply_patches {
	my $self = shift;
	my($patchlet, $proj, $revert, $test, $copy, $verbose) = @_;

	return 1 unless safe_exists($patchlet, ('patch', $proj, 'best'));

	my $projpath = $copy || $self->{projects}->{$proj}->{PATH};

	my @filelist;
	if ($revert) {
		@filelist = reverse @{$patchlet->{patch}->{$proj}->{best}};
	} else {
		@filelist = @{$patchlet->{patch}->{$proj}->{best}};
	}

	for my $file (@filelist) {
		# apply the patch itself
		my $options;
		if ($revert) {
			$options .= "-R ";
		}
		if ($test && !$copy) {
			$options .= "--dry-run ";
		}
		my $patchfile = "$patchlet->{basedir}/$file";
		my $cmd = sprintf("%s -f -p1 -d %s %s < %s", 
				  $BIN_PATCH, $projpath, 
				  $options,
				  $patchfile);
		my $missing_files;
		my $rejects;
		my $notempty;
		my $hunks = count_hunks($patchfile);
		my $patch_output = "";
		open(PATCH, "$cmd|") || die("can't start patch '$cmd': $!\n");
		while (my $line = <PATCH>) {
			# FIXME: parse patch output
			$patch_output .= ">> $line";
			chomp($line);
			if ($line =~ /No file to patch/) {
				$missing_files++;
			} elsif ($line =~ /FAILED at/) {
				$rejects++;
			} elsif ($line =~ /not empty after patch, as expected/) {
				$notempty++;
			}
		}
		close(PATCH);

		if ($test) {
			if ($verbose && (($missing_files != 0) || ($rejects != 0)))
			{
				print "patch output was:\n$patch_output\n";
			}
			if ($missing_files != 0) {
				$self->{ERRMSG} .= "cannot apply $patchfile: ($missing_files missing files)\n";
				return 0;
			# } elsif ($rejects*2 > $hunks) {
			} elsif ($rejects != 0) {
				$self->{ERRMSG} .= "cannot apply $patchfile: ($rejects rejects out of $hunks hunks)\n";
				return 0;
			} else {
				# could be applied!
				#printf(" ALREADY APPLIED $patchfile: (%d rejects out of %d hunks)\n", $rejects, $hunks;
			}
		} else {
			if ($missing_files != 0) {
				$self->{ERRMSG} .= "$patchfile: ERROR ($missing_files missing files)\n";
				return 0;
			} elsif ($rejects != 0) {
				$self->{ERRMSG} .= "$patchfile: ERROR ($rejects rejects out of $hunks hunks)\n";
				return 0;
			}
		}
	}
	return 1;
}

# apply a given patchlet to a given kernel tree
#
# return value:
# 	normal (non-test) mode: 1 on success, 0 on failure
# 	test mode: 1 if test was successful (patch could be applied/reverted)
#	copy: directory with the shadow tree, if any
#	verbose mode: output verbose messages
#
sub apply_patchlet {
	my $self = shift;
	my($patchlet, $revert, $test, $copy, $verbose) = @_;
	my(@projects);

	# print Dumper($patchlet);
	my %projects = ( );
	foreach my $p ( keys %{$patchlet->{files}},
	                keys %{$patchlet->{patch}},
			keys %{$patchlet->{ladds}} ) {
		$projects{$p} = 1;
	}
	@projects = keys %projects;

	foreach my $proj (@projects) {
		for my $file (@{$patchlet->{patch}->{$proj}->{best}}) {
			# Copy source files, if required
			if ($copy && !$self->copy_patchfiles("$patchlet->{basedir}/$file", $copy, $proj)) {
				File::Path::rmtree($copy);
				return 0;
			}
		}

		if (!(($self->apply_newfiles($patchlet, $proj, $revert, $test, $copy)
				 && $self->apply_lineadds($patchlet, $proj, $revert, $test, $copy)
				 && $self->apply_patches($patchlet, $proj, $revert, $test, $copy, $verbose))
			     || ($test
				 && defined $patchlet->{info}->{successor}
				 && defined $self->{patchlets}->{$patchlet->{info}->{successor}}
				 && $self->apply_patchlet($self->{patchlets}->{$patchlet->{info}->{successor}},
						   	  $revert, $test, $copy)))) {
			$copy && File::Path::rmtree($copy);
			return 0;
		}
	}
	map { $self->{last_words}->{$_}++ } @{$patchlet->{info}->{recompile}}
		unless $test || $copy;
	$copy && File::Path::rmtree($copy);
	return 1;
}

# apply a given patchlet to a given kernel tree
#
# return value:
# 	normal (non-test) mode: 1 on success, 0 on failure
# 	test mode: 1 if test was successful (patch could be applied/reverted)
#
sub apply {
	my $self = shift;
	my($patchlet, $revert, $test) = @_;
	my($copy) = '';
	my(@projects);

	if ($test) {
		# Check wether patchlet has got unapplied dependencies
		foreach my $dep (@{$patchlet->{info}->{depends}}) {
			next if $dep =~ /^!/;
			next if grep($_ eq $dep, @{$self->{applied}});
			$copy = "/tmp/pom-$$";
			last;
		}
		# Check broken-out patches
		foreach my $proj (keys %{$patchlet->{patch}}) {
			last if $copy;
			next unless safe_exists($patchlet, ('patch', $proj, 'best'));
			$copy = "/tmp/pom-$$" 
				if $#{$patchlet->{patch}->{$proj}->{best}};
		}
	}
	if ($copy) {
		$test = 0; # otherwise we could not check broken-out patches
		mkdir($copy) or carp "Can't create directory $copy: $!";
		$self->{saved}->{applied} = [ @{$self->{applied}} ] ;
		if (!$self->apply_dependencies($patchlet, 0, 0, $copy)) {
			File::Path::rmtree($copy);
			$self->{applied} = [ @{$self->{saved}->{applied}} ];
			return 0;
		}
	} elsif (!$self->apply_dependencies($patchlet, 0, $test)) {
		return 0;
	}
	
	my $ret = $self->apply_patchlet($patchlet, $revert, $test, $copy);

	if ($copy) {
		File::Path::rmtree($copy);
		$self->{applied} = [ @{$self->{saved}->{applied}} ];
	}

	return $ret;
}

# iterate over all patchlet directories below the given base directory 
# and parse all patchlet definitions
#
sub parse_patchlets {
	my $self = shift;

	my $pomdir = $self->{POM}->{PATH};
	my($patchdir, $patch, @patchlets);

	$patchdir = $pomdir;
	opendir(INDIR, $patchdir)
		or croak "Unable to open $patchdir: $!";
	my @alldirs = grep {!/^\./ && -d "$patchdir/$_" } readdir(INDIR);
	closedir(INDIR);

	foreach my $patch (@alldirs) {
		next unless -f "$patchdir/$patch/info";
		$self->{patchlets}->{$patch} = 
			$self->parse_patchlet("$patchdir/$patch");
	}
}

sub check_versions {
	my @versions = @_;
	my @v;

	foreach my $v (@versions) {
		@v = split(/\./, $v);
		die "Cannot handle update version $v\n"
			if $#v != 2 || $v[2] == 0;
	}
}

sub oldest_version {
	my(@a) = split(/\./, $a);
	my(@b) = split(/\./, $b);

	$a[0] <=> $b[0] && $a[1] <=> $b[1] && $a[2] <=> $b[2];
}

#
# Hash reference behind $self built during a POM session:
#
# session = {
#	POM => directory,
#	projects => { 
#		project => {
#			PATH    => directory,
#			VERSION => version,
#			branches => { id => regexp },
#		},
#	},
#	flags  => { a_flag => 1, },
#	patchlets => { patchlets },
#	applied	  => { applied_patchlets },
# }
sub init {
	my $proto = shift;
	my $class = ref($proto) || $proto;
	my $paths = shift;
	my($proj, $fn);
	my $self = {};

	bless($self, $class);

	# Paths to POM itself and projects
	foreach $proj (keys %$paths) {
		if ($proj eq 'POM') {
			$self->{$proj}->{PATH} = $paths->{$proj};
			next;
		}
		$self->{projects}->{$proj}->{PATH} = $paths->{$proj};
		# get version information of all projects we know of
		$fn = $proj . 'version';
		eval "$fn(\$self)";
	}
	# Flags
	foreach (@_) {
		$self->{flags}->{$_}++;
	}


	# Load config file
	open(CONF, "$paths->{POM}/config")
		or croak "Unable to open $paths->{POM}/config: $!";
	while (<CONF>) {
		chomp;
		my @line = split(/\s+/);
		next unless $line[0] eq 'Branch:';
		# Branch: project id regexp
		croak "Unknown project '$line[1]' in $paths->{POM}/config"
			unless $self->{projects}->{$line[1]};
		croak "Missing id or regexp in $paths->{POM}/config"
			unless $line[3];
		$self->{config}->{$line[1]}->{branches}->{$line[2]} = eval $line[3];
	}
	close(CONF);

	my($branch, $oldest);
	foreach $proj (keys %{$self->{projects}}) {
		foreach $branch (keys %{$self->{config}->{$proj}->{branches}}) {
			$self->{projects}->{$proj}->{branch} = 
				$self->{config}->{$proj}->{branches}->{$branch}
				if $self->{projects}->{$proj}->{VERSION} =~ 
				  /$self->{config}->{$proj}->{branches}->{$branch}/;
		}
		croak "Your $proj version $self->{projects}->{$proj}->{VERSION} is unknown for patch-o-matic"
			unless $self->{projects}->{$proj}->{branch};
	}
	$self->{applied} = [];
	return $self;
}

sub last_words {
	my $self = shift;

	# print anything useful
	print <<TXT if $self->{last_words}->{kernel};
Recompile the kernel image.
TXT
	if ($self->{last_words}->{netfilter}) {	
		if ($self->{last_words}->{kernel}) {
			print <<TXT;
Recompile the netfilter kernel modules.
TXT
		} else {
			print <<TXT;
Recompile the kernel image (if there are non-modular netfilter modules).
Recompile the netfilter kernel modules.
TXT
		}
	}
	print <<TXT if $self->{last_words}->{iptables};
Recompile the iptables binaries.
TXT
}

return 1;

__END__

there are several diffent modes of operation:

=item1 isapplied

tests whether a given kernel tree does already contain a given patch. The only
case where this is true:
	1) all the newfiles do exist
	2) all the lineadds match and their newlines can be found
	3) 'patch -R --dry-run' runs cleanly with no rejected hunks
this is actually the same as 'revert+test' below.

=item1 apply + test

tests whether the given patchlet would apply cleanly to the given tree.  The
only case where this is true:
	1) all the newfiles don't exist
	2) all the lineadd searchlines can be found
	3) 'patch --dry-run' runs cleanly with no rejected hunks

=item1 apply

apply the given patch to the given kernel tree

=item1 revert + test

tests whether the given patchlet would revert cleanly in the given tree. The
only case where this is true:
	1) all the newfiles exist
	2) all the lineadds match and their newlines can be found
	3) 'patch -R --dry-run' runs cleanly with no rejected hunks

=item1 revert

reverts the given patch from the given kernel tree
