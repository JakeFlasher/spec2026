#!/usr/bin/env bash
# clean_stale_spec.sh — reclaim disk space from regenerable SPEC CPU2026 artifacts.
#
# Deletes only artifact classes the SPEC docs bless as regenerable
# (runcpu.txt sections 1.5/1.7, config.txt VIII.A):
#   * per-size run sandboxes   benchspec/CPU/*/run/run_<tune>_<size>_<label>.NNNN
#   * build intermediates      benchspec/CPU/*/build/build_<tune>_<label>.NNNN
#   * runcpu config backups    config/*.cfg.<YYYY-MM-DDTHHMMSS>
#   * dead runcpu scratch      tmp/CPU2026.*
#
# Never touches exe/ (installed binaries), data/ (licensed inputs), src/,
# Spec/, result/ (run provenance), or live *.cfg files.
#
# Dry-run by default: nothing is removed without --apply.
# Refuses to apply while runcpu/specmake/specinvoke processes are alive,
# because a live job owns build dirs, run dirs, and tmp scratch.
#
# Build dirs are only removed when at least one installed binary for the
# same tune+label exists under exe/ — deleting intermediates must never
# cost us a binary that would force a recompile before the ref campaign.
#
# Note: `runcpu --action=clean/trash` exists but cannot select by workload
# size, and `--fake` does NOT dry-run cleaning actions (the docs warn the
# deletion really happens). This script exists to delete *test/train*
# sandboxes while preserving future refrate/refspeed ones, with a real
# dry-run.

set -euo pipefail
shopt -s nullglob

SPEC_ROOT=${SPEC:-/home/jakeshea/speccpu2026/cpu2026}
APPLY=0
FORCE=0
VERBOSE=0
DO_TEST_RUNS=0
DO_REF_RUNS=0
DO_BUILDS=0
DO_CFG_BACKUPS=0
DO_TMP=0
LABEL_FILTER=""

usage() {
    cat <<'EOF'
Usage: clean_stale_spec.sh [options] [categories]

Categories (default when none given: --test-runs --cfg-backups --tmp):
  --test-runs     run dirs for the test and train workloads
  --ref-runs      run dirs for refrate/refspeed workloads (off by default;
                  use between RRR sweeps — RRR creates one run dir per
                  benchmark x copy x iteration)
  --builds        build intermediate dirs (only where exe/ still holds a
                  binary for the same tune+label)
  --cfg-backups   timestamped config/*.cfg.<date>T<time> backups runcpu
                  writes every time it updates a config's hash section
  --tmp           tmp/CPU2026.* scratch (only when no SPEC process is alive)
  --all           --test-runs --builds --cfg-backups --tmp

Options:
  --spec-root DIR  SPEC install root (default: $SPEC or /home/jakeshea/speccpu2026/cpu2026)
  --label STR      only touch run/build dirs whose label contains STR
                   (e.g. mytest_gcc); cfg-backups/tmp are not label-scoped
  --apply          actually delete (default: dry run, prints what would go)
  --force          override the active-SPEC-process refusal (dangerous)
  --verbose        list every path, not just per-category summaries
  -h, --help       this text
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --test-runs)   DO_TEST_RUNS=1 ;;
        --ref-runs)    DO_REF_RUNS=1 ;;
        --builds)      DO_BUILDS=1 ;;
        --cfg-backups) DO_CFG_BACKUPS=1 ;;
        --tmp)         DO_TMP=1 ;;
        --all)         DO_TEST_RUNS=1; DO_BUILDS=1; DO_CFG_BACKUPS=1; DO_TMP=1 ;;
        --spec-root)   SPEC_ROOT=$2; shift ;;
        --label)       LABEL_FILTER=$2; shift ;;
        --apply)       APPLY=1 ;;
        --force)       FORCE=1 ;;
        --verbose)     VERBOSE=1 ;;
        -h|--help)     usage; exit 0 ;;
        *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [ "$DO_TEST_RUNS$DO_REF_RUNS$DO_BUILDS$DO_CFG_BACKUPS$DO_TMP" = "00000" ]; then
    DO_TEST_RUNS=1; DO_CFG_BACKUPS=1; DO_TMP=1
fi

[ -d "$SPEC_ROOT/benchspec/CPU" ] || { echo "not a SPEC CPU2026 install: $SPEC_ROOT" >&2; exit 2; }

active_spec_processes() {
    pgrep -af 'runcpu|specinvoke|specmake' 2>/dev/null | grep -v "clean_stale_spec" || true
}

ACTIVE=$(active_spec_processes)
if [ -n "$ACTIVE" ]; then
    echo "WARNING: live SPEC processes detected:"
    echo "$ACTIVE" | sed 's/^/    /'
    if [ "$APPLY" = 1 ] && [ "$FORCE" = 0 ]; then
        echo "Refusing to --apply while a runcpu job is active (it owns run/build/tmp dirs)." >&2
        echo "Wait for it to finish, or pass --force if you are certain." >&2
        exit 1
    fi
fi

declare -a TEST_RUN_TARGETS REF_RUN_TARGETS BUILD_TARGETS CFG_TARGETS TMP_TARGETS SKIPPED
declare -A AFFECTED_PARENTS

# run_<tune>_<size>_<label>.NNNN / build_<tune>_<label>.NNNN
# tune is a single token (base|peak); the remainder up to the final
# .NNNN suffix is the user-chosen label, which may itself contain '_'.
collect_run_dirs() {
    local d name rest tune size label
    for d in "$SPEC_ROOT"/benchspec/CPU/*/run/run_*; do
        [ -d "$d" ] || continue
        name=$(basename "$d")
        rest=${name#run_}
        tune=${rest%%_*}; rest=${rest#*_}
        size=${rest%%_*}; rest=${rest#*_}
        label=${rest%.*}
        [ -n "$LABEL_FILTER" ] && [[ $label != *"$LABEL_FILTER"* ]] && continue
        case "$size" in
            test|train)        [ "$DO_TEST_RUNS" = 1 ] && { TEST_RUN_TARGETS+=("$d"); AFFECTED_PARENTS[$(dirname "$d")]=1; } ;;
            refrate|refspeed)  [ "$DO_REF_RUNS" = 1 ]  && { REF_RUN_TARGETS+=("$d");  AFFECTED_PARENTS[$(dirname "$d")]=1; } ;;
        esac
    done
}

collect_build_dirs() {
    local d name rest tune label bench_dir exe_match
    for d in "$SPEC_ROOT"/benchspec/CPU/*/build/build_*; do
        [ -d "$d" ] || continue
        name=$(basename "$d")
        rest=${name#build_}
        tune=${rest%%_*}; rest=${rest#*_}
        label=${rest%.*}
        [ -n "$LABEL_FILTER" ] && [[ $label != *"$LABEL_FILTER"* ]] && continue
        bench_dir=$(dirname "$(dirname "$d")")
        exe_match=("$bench_dir"/exe/*"_${tune}.${label}")
        if [ ${#exe_match[@]} -eq 0 ] && [ "$FORCE" = 0 ]; then
            SKIPPED+=("$d  (no exe/*_${tune}.${label} — deleting would force a recompile)")
            continue
        fi
        BUILD_TARGETS+=("$d")
        AFFECTED_PARENTS[$(dirname "$d")]=1
    done
}

collect_cfg_backups() {
    local f
    for f in "$SPEC_ROOT"/config/*.cfg.????-??-??T??????; do
        [ -f "$f" ] && CFG_TARGETS+=("$f")
    done
}

collect_tmp() {
    if [ -n "$ACTIVE" ]; then
        SKIPPED+=("$SPEC_ROOT/tmp/*  (live runcpu job owns scratch here — skipped even with --force)")
        return
    fi
    local p
    for p in "$SPEC_ROOT"/tmp/*; do
        TMP_TARGETS+=("$p")
    done
}

[ "$DO_TEST_RUNS" = 1 ] || [ "$DO_REF_RUNS" = 1 ] && collect_run_dirs
[ "$DO_BUILDS" = 1 ] && collect_build_dirs
[ "$DO_CFG_BACKUPS" = 1 ] && collect_cfg_backups
[ "$DO_TMP" = 1 ] && collect_tmp

sum_kb() {
    [ $# -eq 0 ] && { echo 0; return; }
    du -sk "$@" 2>/dev/null | awk '{s+=$1} END {print s+0}'
}

human() {
    awk -v kb="$1" 'BEGIN {
        if (kb >= 1048576)    printf "%.1fG", kb/1048576
        else if (kb >= 1024)  printf "%.1fM", kb/1024
        else                  printf "%dK", kb
    }'
}

TOTAL_KB=0
report_category() {
    local title=$1; shift
    local n=$#
    [ "$n" -eq 0 ] && return
    local kb; kb=$(sum_kb "$@")
    TOTAL_KB=$((TOTAL_KB + kb))
    printf '%-22s %5d items  %8s\n' "$title" "$n" "$(human "$kb")"
    if [ "$VERBOSE" = 1 ]; then
        printf '    %s\n' "$@"
    fi
}

echo
echo "SPEC root: $SPEC_ROOT   mode: $([ "$APPLY" = 1 ] && echo APPLY || echo DRY-RUN)"
echo
report_category "test/train run dirs" "${TEST_RUN_TARGETS[@]+"${TEST_RUN_TARGETS[@]}"}"
report_category "ref run dirs"        "${REF_RUN_TARGETS[@]+"${REF_RUN_TARGETS[@]}"}"
report_category "build dirs"          "${BUILD_TARGETS[@]+"${BUILD_TARGETS[@]}"}"
report_category "config backups"      "${CFG_TARGETS[@]+"${CFG_TARGETS[@]}"}"
report_category "tmp scratch"         "${TMP_TARGETS[@]+"${TMP_TARGETS[@]}"}"
echo "----------------------------------------------"
printf '%-22s %18s\n' "reclaimable" "$(human "$TOTAL_KB")"

if [ ${#SKIPPED[@]} -gt 0 ]; then
    echo
    echo "Skipped (protective guards):"
    printf '    %s\n' "${SKIPPED[@]}"
fi

if [ "$APPLY" = 0 ]; then
    echo
    echo "Dry run only. Re-run with --apply to delete."
    exit 0
fi

# The run/list and build/list files index the numbered dirs; runcpu trusts
# them when reusing dirs, so entries for deleted dirs must go too. The docs
# bless removing the whole run// build/ dir, so an emptied parent is pruned.
rewrite_list_file() {
    local parent=$1 listfile=$1/list
    [ -f "$listfile" ] || return 0
    awk -v parent="$parent" '
        body == 1   { print; next }
        /^__END__/  { body = 1; print; next }
        {
            if (system("test -d \"" parent "/" $1 "\"") == 0) print
        }
    ' "$listfile" > "$listfile.tmp" && mv "$listfile.tmp" "$listfile"
}

prune_if_empty() {
    local parent=$1
    local leftover
    leftover=$(find "$parent" -mindepth 1 -maxdepth 1 ! -name list 2>/dev/null | head -1)
    [ -z "$leftover" ] && rm -rf "$parent"
}

delete_all() {
    local p
    for p in "$@"; do
        rm -rf "$p"
        [ "$VERBOSE" = 1 ] && echo "deleted: $p"
    done
}

echo
delete_all "${TEST_RUN_TARGETS[@]+"${TEST_RUN_TARGETS[@]}"}"
delete_all "${REF_RUN_TARGETS[@]+"${REF_RUN_TARGETS[@]}"}"
delete_all "${BUILD_TARGETS[@]+"${BUILD_TARGETS[@]}"}"
delete_all "${CFG_TARGETS[@]+"${CFG_TARGETS[@]}"}"
delete_all "${TMP_TARGETS[@]+"${TMP_TARGETS[@]}"}"

for parent in "${!AFFECTED_PARENTS[@]}"; do
    [ -d "$parent" ] || continue
    rewrite_list_file "$parent"
    prune_if_empty "$parent"
done

echo "Done. Freed approximately $(human "$TOTAL_KB")."
