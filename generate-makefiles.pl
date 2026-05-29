#!/usr/bin/env perl
use strict;
use warnings;
use Cwd 'abs_path';

# Generates Makefile.spec and Makefile.deps from Spec/object.pm files.
# Supports out-of-tree builds via OUTPUT_DIR environment variable.
#
# Usage:
#   OUTPUT_DIR=build/gcc-O3 ./generate-makefiles.pl [benchmark_id ...]
#
# Environment variables:
#   SPEC        - SPEC root
#   OUTPUT_DIR  - base output directory (default: src dir of each benchmark)
#   CC, CXX, FC - compilers
#   COPT, CXXOPT, FOPT - optimization flags
#   LDFLAGS, XLD       - linker flags
#   XCFLAGS, XCXXFLAGS, XFFLAGS - extra flags
#   PORT        - portability flags
#   DEFINE      - extra -D defines

my $spec = $ENV{SPEC} || abs_path('.');
my $cpu = "$spec/benchspec/CPU";
my $output_base = $ENV{OUTPUT_DIR} || '';

# Simulate Perl's Config module for byteorder detection.
# Used by several benchmarks in their bench_flags.
{
    package Config;
    our %Config = (byteorder => '1234');
}

# Also make it available to the eval in the main package
package main;
our %Config = (byteorder => '1234');

my $CC       = $ENV{CC}       || 'gcc';
my $CXX      = $ENV{CXX}      || 'g++';
my $FC       = $ENV{FC}       || 'gfortran';
my $COPT     = $ENV{COPT}     || '-O3';
my $CXXOPT   = $ENV{CXXOPT}   || $COPT;
my $FOPT     = $ENV{FOPT}     || $COPT;
my $LDFLAGS  = $ENV{LDFLAGS}  || '';
my $XCFLAGS  = $ENV{XCFLAGS}  || '';
my $XCXXFLAGS = $ENV{XCXXFLAGS} || '';
my $XFFLAGS  = $ENV{XFFLAGS}  || '';
my $XLD      = $ENV{XLD}      || '';
my $PORT     = $ENV{PORT}     || '';
my $DEFINE   = $ENV{DEFINE}   || '';
my $XLIBS    = $ENV{XLIBS}    || '';

# Portability flags extracted from default.cfg — per-benchmark overrides.
# Keyed by benchmark number (e.g. "710" matches 710.omnetpp_r and 710.omnetpp_s).
my %PORTABILITY = (
    '800' => '-DSPEC_SUPPRESS_LOCAL_AND_REDUCE',
    '710' => '-fno-finite-math-only',
    '734' => '-fno-finite-math-only',
    '834' => '-fno-finite-math-only',
    '735' => '-fno-finite-math-only -Ulinux',
    '835' => '-fno-finite-math-only -Ulinux',
    '736' => '-fno-finite-math-only',
    '737' => '-fno-fast-math',
    '748' => '-fno-fast-math',
    '753' => '-fno-finite-math-only',
    '853' => '-fno-finite-math-only',
    '767' => '-fno-finite-math-only',
    '867' => '-fno-finite-math-only',
);
# PORTABILITY_LIBS per benchmark
my %PORTABILITY_LIBS = (
    '767' => '-lstdc++fs',
    '867' => '-lstdc++fs',
);

sub find_bench_dir {
    my ($id) = @_;
    opendir(my $dh, $cpu) or return undef;
    while (my $e = readdir($dh)) {
        if ($e =~ /^\Q$id\E\./ || $e eq $id) {
            closedir($dh);
            return "$cpu/$e";
        }
    }
    closedir($dh);
    return undef;
}

sub generate_makefiles {
    my ($pm_file) = @_;
    my $bench_dir = $pm_file;
    $bench_dir =~ s|/Spec/object\.pm$||;

    open(my $fh, '<', $pm_file) or do { warn "Cannot open $pm_file: $!\n"; return; };
    my $content = do { local $/; <$fh> };
    close($fh);

    my $stripped = $content;
    $stripped =~ s/^sub\s+\w+.*?^}\n//gms;
    $stripped =~ s/^1;\s*$//m;
    $stripped =~ s/^use\s+Config\s*;\s*$//m;
    $stripped =~ s/^use\s+Cwd\s*;\s*$//m;

    # Reset package variables before eval to prevent stale values
    # from a previous benchmark's eval leaking through.
    no strict 'vars';
    $main::benchnum = $main::benchname = $main::exename = $main::benchlang = '';
    $main::need_math = $main::bench_flags = $main::bench_cxxflags = '';
    $main::bench_fflags = $main::bench_fppflags = '';
    @main::sources = ();
    @main::base_exe = ();
    %main::sources = ();
    %main::common_sources = ();
    %main::deps = ();
    %main::srcdeps = ();

    {
        my $ok = eval $stripped;
        if ($@) {
            warn "  Eval error in $pm_file: $@\n";
            return;
        }
    }

    my $benchnum     = $main::benchnum     // '';
    my $benchname    = $main::benchname    // '';
    my $exename      = $main::exename      // '';
    my $benchlang    = $main::benchlang    // '';
    my $need_math    = $main::need_math    // '';
    my $bench_flags  = $main::bench_flags  // '';
    my $bench_cxxflags = $main::bench_cxxflags // '';
    my $bench_fflags = $main::bench_fflags // '';
    my $bench_fppflags = $main::bench_fppflags // '';
    my @sources      = @main::sources;
    my @base_exe     = @main::base_exe;
    my %multi_src    = %main::sources;
    my %common_sources = %main::common_sources;

    @base_exe = ($exename) unless @base_exe;

    if (!@sources && %multi_src) {
        my $primary = $base_exe[0];
        if (exists $multi_src{$primary}) {
            @sources = @{$multi_src{$primary}};
        } else {
            my @keys = keys %multi_src;
            @sources = @{$multi_src{$keys[0]}};
        }
    }

    if (!@sources) {
        warn "  No sources for $benchnum.$benchname ($pm_file)\n";
        return;
    }

    my $bf = $bench_flags;

    my $src_dir = "$bench_dir/src";
    my $bid = (split('/', $bench_dir))[-1];

    # Determine output directory
    my $out_dir;
    if ($output_base) {
        $out_dir = "$output_base/$bid";
    } else {
        $out_dir = $src_dir;
    }
    mkdir($out_dir) unless -d $out_dir;

    # Exe name with optional .exe
    my $exe_name = $exename;

    # Per-benchmark portability flags from config
    my $pflags = $PORT;
    my $plibs  = '';
    if (exists $PORTABILITY{$benchnum}) {
        $pflags = $pflags ? "$pflags $PORTABILITY{$benchnum}" : $PORTABILITY{$benchnum};
    }
    if (exists $PORTABILITY_LIBS{$benchnum}) {
        $plibs = $PORTABILITY_LIBS{$benchnum};
    }

    # Default EXTRA_FFLAGS for Fortran benchmarks
    my $xfflags = $XFFLAGS;
    if ($benchlang =~ /F/i && $xfflags !~ /fallow-argument-mismatch/ && $FC !~ /flang-new/) {
        $xfflags = $xfflags ? "$xfflags -fallow-argument-mismatch" : "-fallow-argument-mismatch";
    }

    # Collect compile flags
    my @flag_lines;
    push @flag_lines, "BENCH_FLAGS = $bf" if $bf;
    push @flag_lines, "BENCH_CXXFLAGS = $bench_cxxflags" if $bench_cxxflags;
    push @flag_lines, "BENCH_FFLAGS = $bench_fflags" if $bench_fflags;
    push @flag_lines, "BENCH_FPPFLAGS = $bench_fppflags" if $bench_fppflags;
    push @flag_lines, "CC  = $CC";
    push @flag_lines, "CXX = $CXX";
    push @flag_lines, "FC  = $FC";
    push @flag_lines, "COPTIMIZE   = $COPT";
    push @flag_lines, "CXXOPTIMIZE = $CXXOPT";
    push @flag_lines, "FOPTIMIZE   = $FOPT";
    push @flag_lines, "LDFLAGS = $LDFLAGS" if $LDFLAGS;
    push @flag_lines, "EXTRA_LDFLAGS = $XLD" if $XLD;
    push @flag_lines, "EXTRA_CFLAGS = $XCFLAGS" if $XCFLAGS;
    push @flag_lines, "EXTRA_CXXFLAGS = $XCXXFLAGS" if $XCXXFLAGS;
    push @flag_lines, "EXTRA_FFLAGS = $xfflags" if $xfflags;
    push @flag_lines, "PORTABILITY = $pflags" if $pflags;
    push @flag_lines, "EXTRA_LIBS = $plibs" if $plibs;
    push @flag_lines, "NEED_MATH = yes" if $need_math && $need_math =~ /yes/i;
    if ($XLIBS) {
        push @flag_lines, "EXTRA_LIBS += $XLIBS";
    }
    if ($DEFINE) {
        (my $d = $DEFINE) =~ s/^["']//; $d =~ s/["']$//;
        push @flag_lines, "EXTRA_CFLAGS += $d";
        push @flag_lines, "EXTRA_CXXFLAGS += $d";
    }

    # Convert commas to spaces in BENCHLANG.  Makefile.defaults uses
    # $(firstword) which splits on whitespace, and later constructs
    # variable names like $(PRIMARY_BENCHLANG)C for the linker.
    # With a comma (e.g. "CXX,C") the whole string becomes the
    # "first word" and the constructed variable name is wrong.
    (my $bl = $benchlang) =~ tr/,/ /;

    # Generate a subdirectory per exe in @base_exe, each with its own
    # Makefile.spec pointing at the right EXEBASE and SOURCES.
    my @exe_list = @base_exe;
    @exe_list = ($exe_name) unless @exe_list;
    my $rel_out = $out_dir;
    $rel_out =~ s|^\Q$spec\E/||;
    for my $exe (@exe_list) {
        my @src_for_exe = $exe eq $exe_name
            ? @sources
            : (exists $multi_src{$exe} ? @{$multi_src{$exe}} : ());
        next unless @src_for_exe;

        my $exe_dir = "$out_dir/$exe";
        mkdir($exe_dir) unless -d $exe_dir;

        my @objs_for_exe = map { my $o = $_; $o =~ s/\.[^.]+$/\$(OBJ)/; $o } @src_for_exe;

        # Symlink all source files (including the original Makefile).
        # Then write only files that don't exist in the source tree.
        symlink_src($src_dir, $exe_dir);

        open(my $sfh, '>', "$exe_dir/Makefile.spec")
            or die "Cannot write $exe_dir/Makefile.spec: $!";
        print $sfh "# Auto-generated\n";
        print $sfh "BENCHLANG  = $bl\n";
        print $sfh "EXEBASE    = $exe\n";
        print $sfh "SOURCES    = @src_for_exe\n";
        print $sfh "\n";
        print $sfh join("\n", @flag_lines) . "\n";
        print $sfh "\n";
        close($sfh);

        open(my $dfh, '>', "$exe_dir/Makefile.deps")
            or die "Cannot write $exe_dir/Makefile.deps: $!";
        print $dfh "# Auto-generated\n";
        print $dfh "\n";

        # Generate Fortran USE dependency rules from %deps.
        # Each rule ensures a target object file depends on its preprocessed
        # source and on the object files of all modules it USEs.
        my %deps = %main::deps;
        if (%deps) {
            for my $src (sort keys %deps) {
                my @dlist = @{$deps{$src}};
                next unless @dlist;
                my ($tgt_name, $tgt_src) = fppized_info($src);
                my @dep_names;
                for my $dep (@dlist) {
                    my ($dep_name) = fppized_info($dep);
                    push @dep_names, $dep_name;
                }
                print $dfh "\$(addsuffix \$(OBJ),$tgt_name): $tgt_src \$(addsuffix \$(OBJ)," . (join ' ', @dep_names) . ")\n";
            }
        }

        print $dfh "\n";
        close($dfh);

        printf "  %-25s %-8s %s in %s/\n",
            "$benchnum.$benchname", "[$benchlang]", $exe,
            "$rel_out/$exe";
    }
}

# Returns (fppized_basename, preprocessed_source) for a given source file.
# For uppercase-F Fortran files (.F90/.F95/.F77/.F) that need preprocessing:
#   ("basename.fppized", "basename.fppized.f90")
# For all other files (lowercase .f90, .c, .cc, etc.):
#   ("basename", "original_filename")
sub fppized_info {
    my ($file) = @_;
    my ($base, $ext) = $file =~ /^(.*)(\.[^.]+)$/;
    if (defined $ext && $ext =~ /^\.F(?:90|95|77)?$/) {
        my $low = lc($ext);
        return ("${base}.fppized", "${base}.fppized${low}");
    } else {
        return (defined $base ? $base : $file, $file);
    }
}

sub symlink_src {
    my ($src_dir, $out_dir) = @_;
    opendir(my $dh, $src_dir) or do { warn "Cannot open $src_dir: $!\n"; return; };
    my @entries = readdir($dh);
    closedir($dh);
    foreach my $e (@entries) {
        next if $e eq '.' || $e eq '..';
        my $src_path = "$src_dir/$e";
        my $dst_path = "$out_dir/$e";
        next if -e $dst_path;
        if (-d $src_path) {
            mkdir($dst_path);
            symlink_src($src_path, $dst_path);
        } else {
            symlink($src_path, $dst_path) or warn "  Cannot symlink $src_path: $!\n";
        }
    }
}

# Main
my @pm_files;
if (@ARGV) {
    foreach my $b (@ARGV) {
        my $dir = find_bench_dir($b);
        if ($dir) {
            push @pm_files, "$dir/Spec/object.pm";
        } else {
            warn "Benchmark '$b' not found\n";
        }
    }
} else {
    @pm_files = sort <$cpu/*/Spec/object.pm>;
}

foreach my $pm (@pm_files) {
    generate_makefiles($pm);
}
