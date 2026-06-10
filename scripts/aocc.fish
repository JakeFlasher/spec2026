# AOCC environment toggle for fish — session-local, not autoloaded.
# Usage:  source aocc.fish; aocc on | off | status
function aocc --description 'Toggle the AMD AOCC compiler environment for this session'
    set -l aocc_root /opt/aocc
    # Every variable touched by /opt/aocc/setenv_AOCC.sh; snapshotted on
    # 'on' so 'off' restores the exact pre-AOCC state (including unset).
    set -l vars PATH LIBRARY_PATH LD_LIBRARY_PATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH

    switch "$argv[1]"
        case on
            if set -q __aocc_active
                echo "aocc: already active in this session (run 'aocc off' first)"
                return 1
            end
            if not test -x $aocc_root/bin/clang
                echo "aocc: $aocc_root/bin/clang not found" >&2
                return 1
            end

            for v in $vars
                if set -q $v
                    set -g __aocc_saved_$v $$v
                    set -g __aocc_had_$v 1
                end
            end

            # Same final ordering as setenv_AOCC.sh after all its prepends
            set -gx --path LIBRARY_PATH $aocc_root/lib $aocc_root/lib32 /usr/lib64 /usr/lib /usr/lib32 $LIBRARY_PATH
            set -gx --path LD_LIBRARY_PATH $aocc_root/ompd $aocc_root/lib $aocc_root/lib32 /usr/lib64 /usr/lib /usr/lib32 $LD_LIBRARY_PATH
            set -gx PATH $aocc_root/share/opt-viewer $aocc_root/bin $PATH
            set -gx --path C_INCLUDE_PATH $C_INCLUDE_PATH $aocc_root/include
            set -gx --path CPLUS_INCLUDE_PATH $CPLUS_INCLUDE_PATH $aocc_root/include

            set -g __aocc_active 1
            echo "aocc: loaded — "(clang --version | head -n1)

        case off
            if not set -q __aocc_active
                echo "aocc: not active in this session"
                return 1
            end
            for v in $vars
                set -l saved __aocc_saved_$v
                set -l had __aocc_had_$v
                if set -q $had
                    set -gx $v $$saved
                else
                    set -e $v
                end
                set -e $saved
                set -e $had
            end
            set -e __aocc_active
            echo "aocc: environment restored — clang is now "(command -s clang; or echo "not on PATH")

        case status ''
            if set -q __aocc_active
                echo "aocc: active ("(command -s clang)")"
            else
                echo "aocc: inactive ("(command -s clang; or echo "no clang on PATH")")"
            end

        case '*'
            echo "usage: aocc on|off|status" >&2
            return 2
    end
end
