#
#  shrc.fish - sets up the environment to run SPEC CPU from the fish shell.
#  Port of the Bourne-shell `shrc` shipped with SPEC CPU2026 v1.0.1.
#
#  Usage:  cd to your SPEC CPU2026 install directory, then
#              source shrc.fish
#
#  Local convenience port for this install only -- do not redistribute
#  (the original shrc is SPEC-licensed material).
#
set -g UCSUITE CPU2026

umask 002

# Set the locale, if it isn't already set and the user hasn't forbidden it
if not set -q SPEC_LOCALE_OK
    if not set -q LC_ALL; or not set -q LC_LANG
        set -gx LC_ALL C
        set -gx LC_LANG C
    end
end

# Ignore any preset SPEC variable; find the top of the SPEC hierarchy by
# walking up from the current directory until bin/harness/runcpu appears.
set -e SPEC
set -l tempspec (pwd)
while not test -f "$tempspec/bin/harness/runcpu"
        and test "$tempspec" != /; and test "$tempspec" != .
    set tempspec (dirname $tempspec)
end

if test -f "$tempspec/bin/harness/runcpu"
    set -gx SPEC $tempspec
else
    echo "Can't find the top of your SPEC tree: "(pwd)"/bin/harness/runcpu"
    echo "was not found!  Please change to your $UCSUITE directory and source"
    echo "shrc.fish again."
    return 1
end

if not test -x "$SPEC/bin/specperl"; and not test -x "$SPEC/bin/specperl.exe"
    echo ""
    echo "WARNING: this benchmark tree has not yet been installed.  Please"
    echo "         run install.sh before continuing."
    echo ""
end

# Discourage sourcing this on read-only distribution media: the config
# directory must be writable for the tree to be usable for runs.
if touch "$SPEC/config/shrc$fish_pid"writetest 2>/dev/null
    rm -f "$SPEC/config/shrc$fish_pid"writetest 2>/dev/null
else
    echo "You are not allowed to write into $SPEC/config."
    echo "That may be because you are attempting to source the shrc on your distribution"
    echo "media."
    echo
    echo "It may also be that a different user installed the benchmark tree and"
    echo "has not set permissions that allow you to use it for runs.  See the"
    echo "output_root section of runcpu.html for information on how an installed"
    echo "benchmark tree may be used by multiple users."
    echo
    echo "Please try again after correcting the problem."
    set -e SPEC
    return 1
end

if not contains -- $SPEC/bin $PATH
    set -gx PATH $SPEC/bin $PATH
end

# SPECPERLLIB: colon-joined list of the perl library dirs that exist
set -l perllib
for i in $SPEC/common $SPEC/bin/lib $SPEC/bin $SPEC/bin/lib/5* \
         $SPEC/bin/lib/site_perl $SPEC/bin/lib/site_perl/5*
    if test -d $i; and not contains -- $i $perllib
        set -a perllib $i
    end
end
set -gx SPECPERLLIB (string join : $perllib)

# Only needed when specperl is dynamically linked against libperl
for i in $SPEC/bin $SPEC/bin/lib
    set -l libs $i/libperl.so*
    if set -q libs[1]
        set -l parts (string split -n : -- "$LD_LIBRARY_PATH")
        if not contains -- $i $parts
            set -gx LD_LIBRARY_PATH (string join : $parts $i)
        end
    end
end

function __spec_go_usage
    set -l me $argv[1]
    set -l mytop '$SPEC'
    if test "$me" = ogo
        if string match -q '/*' -- "$GO"
            set mytop '$GO'
        else
            set mytop '$SPEC/$GO'
        end
    end
    echo "Usage: $me <destination>"
    echo "Destinations:"
    echo " top              : $mytop"
    echo ' docs             : $SPEC/Docs'
    echo ' config           : $SPEC/config'
    echo " result           : $mytop/result"
    echo " <benchmark> [...]: $mytop/benchspec/CPU/<benchmark>"
    echo " benchmark can be abbreviated: e.g. '$me 999'"
    echo "See utility.html#$me for more information."
    echo
    echo "\$SPEC is currently set to \"$SPEC\""
    if test "$me" = ogo
        echo "\$GO is currently set to \"$GO\""
    end
    echo
end

# Resolve a (possibly abbreviated) benchmark name to a directory.
# Result is communicated through the global __spec_tmp, mirroring the
# SPECTMP variable used by the original shrc.
function __spec_whichbench
    set -g __spec_tmp ''
    set -l top $argv[1]
    set -l bench $argv[2]
    set -l me go
    if test "$__spec_no_go" != 1
        set me ogo
    end
    if test -z "$bench"
        # No benchmark specified; infer the current one from $PWD, checking
        # the chosen top, the output root, and the main tree.
        set -l gogo $SPEC
        if test "$__spec_no_go" != 1
            if string match -q '/*' -- "$GO"
                set gogo $GO
            else
                set gogo (string replace -ra '//*' '/' -- "$SPEC/$GO")
            end
        end
        for i in $top $gogo $SPEC
            set bench (pwd | sed "s#$i//*benchspec/[^/][^/]*/##; s#/.*##;")
            if test -n "$bench"
                break
            end
        end
        if test -z "$bench"
            set -g __spec_tmp .
            return
        end
    end
    for i in $top/benchspec/*/$bench* $top/benchspec/*/0$bench* \
             $top/benchspec/*/00$bench* $top/benchspec/*/*.$bench*
        if test -d $i
            set -g __spec_tmp $i
            return
        end
    end
    echo "Can't resolve \"$bench\" into a benchmark name"
    echo
    echo "Try '$me --help' for options"
    echo
end

function __spec_do_go
    set -l root $argv[1]
    set -e argv[1]
    set -l dest $argv[1]
    set -l rest $argv[2..]
    switch "$dest"
        case top ''
            cd $root; or return
        case bin
            cd $root/bin; or return
        case config
            cd $root/config; or return
        case doc Doc docs Docs
            cd $root/Docs; or return
        case result results
            cd $root/result; or return
        case int fp cpu
            cd $root/benchspec/CPU*; or return
        case mpi
            cd $root/benchspec/MPI*; or return
        case src build run data exe Spec
            __spec_whichbench $root
            if test -n "$__spec_tmp"; and test "$__spec_tmp" != .
                cd $__spec_tmp; or return
                if test -d $dest
                    cd $dest
                else
                    echo "No directory named \"$dest\""
                    return 1
                end
            else if test -n "$rest[1]"; and test -z "$__spec_no_recurse"
                # "go src 999" given outside a benchmark tree: retry as
                # "go 999 src" (benchmark first, then subdirectory)
                set -g __spec_no_recurse 1
                __spec_do_go $root $rest[1] $dest $rest[2..]
                set -l ret $status
                set -e __spec_no_recurse
                return $ret
            else
                echo Not in a benchmark tree
                return 1
            end
            return 0
        case '*'
            __spec_whichbench $root $dest
            if test -n "$__spec_tmp"
                cd $__spec_tmp; or return
            else
                # No benchmark found; do not attempt to do subdirs
                return 1
            end
    end
    for subdir in $rest
        if test -d $subdir
            cd $subdir
        else
            echo "No directory named \"$subdir\""
            return 1
        end
    end
end

function __spec_check_output_root
    if test -z "$GO"; or test "$GO" = "$SPEC"
        # If $GO is empty or $SPEC, then there can't be a mismatch
        return 0
    end
    set -l _go
    if string match -q '/*' -- "$GO"
        set _go $GO
    else
        set _go (string replace -ra '//*' '/' -- "$SPEC/$GO")
    end
    if not test -d $_go
        echo "Unable to locate directory named by GO ($GO)"
        return 1
    end
    if not test -f $_go/version.txt
        # Check not possible; assume it's okay
        return 0
    end
    if not test -r $_go/version.txt
        return 1
    end
    set -l or_suite (sed 's/^SPEC[[:space:]]*//; s/[[:space:]].*//' $_go/version.txt)
    set -l or_version (sed -e 's/^.*[[:space:]]\([^[:space:]][^[:space:]]*\)$/\1/' -e 's/dev$//' $_go/version.txt)
    set -l my_suite (echo $UCSUITE | sed 's/^SPEC[[:space:]]*//; s/[[:space:]].*//')
    set -l my_version (cat $SPEC/version.txt)
    if test "$or_version" != "$my_version"; or test "$or_suite" != "$my_suite"
        echo "ERROR: GO directory ($_go) version mismatch"
        echo "       GO   is from SPEC $or_suite v$or_version"
        echo "       SPEC is from SPEC $my_suite v$my_version"
        echo "       Please adjust your setting for the GO environment variable"
        return 1
    end
    return 0
end

function go --description 'cd around the SPEC tree (utility.html#go)'
    set -g __spec_no_go 1
    if test -z "$SPEC"
        echo
        echo "The SPEC environment variable is not set! Please source shrc.fish and try again."
        echo
        return 1
    end
    if test "$argv[1]" = --help; or test "$argv[1]" = -h
        __spec_go_usage go
    else
        __spec_do_go $SPEC $argv
        pwd
    end
end

function ogo --description 'cd around the SPEC output root in $GO (utility.html#ogo)'
    set -g __spec_no_go 0
    if test -z "$SPEC"
        echo
        echo "The SPEC environment variable is not set! Please source shrc.fish and try again."
        echo
        return 1
    end
    if test "$argv[1]" = --help; or test "$argv[1]" = -h
        __spec_go_usage ogo
    else
        if __spec_check_output_root
            set -l top $SPEC
            if test -n "$GO"
                set -l _go
                if string match -q '/*' -- "$GO"
                    set _go $GO
                else
                    set _go (string replace -ra '//*' '/' -- "$SPEC/$GO")
                end
                switch "$argv[1]"
                    case top ''
                        if test -z "$OGO_NO_WARN"
                            echo "Using value in GO for output_root: $_go"
                        end
                        set top $_go
                    case bin config doc Doc docs Docs int fp cpu mpi src data
                        # These live in the main tree, not the output root
                    case '*'
                        switch "$argv[2]"
                            case data src Spec
                            case '*'
                                if test -z "$OGO_NO_WARN"
                                    echo "Using value in GO for output_root: $GO"
                                end
                                set top $_go
                        end
                end
            end
            __spec_do_go $top $argv
            pwd
        end
    end
end
