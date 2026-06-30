#!/usr/bin/env bash
# install.sh — set up the modernization toolkit on the pod, in one of two MODES, with a CLEAN install.
#
#   bash install.sh full       # React + Spring Boot   (agent: modernize-flow ; 4 skills)   [default]
#   bash install.sh frontend   # React only (fallback) (agent: jsp2react      ; 3 skills)
#
# CLEAN install: it first REMOVES this toolkit's managed skills + agents (and the retired v2 agents) from the
# target dirs, then installs exactly the set for the chosen mode — so the pod is never left running stale files.
# It only ever touches files THIS toolkit owns (by name); your other ~/.copilot skills/agents are untouched.
#
# Override targets if your pod differs:  COPILOT_SKILLS_DIR=… COPILOT_AGENTS_DIR=… bash install.sh <mode>
# (Once DigitCode packaging is ready, `dc agent install modernize-flow` replaces this script.)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

MODE="${1:-full}"
case "$MODE" in
  full|frontend) ;;
  *) echo "usage: bash install.sh [full|frontend]   (got '$MODE')"; exit 1 ;;
esac

SKILLS_DST="${COPILOT_SKILLS_DIR:-$HOME/.copilot/skills}"
AGENTS_DST="${COPILOT_AGENTS_DIR:-$HOME/.copilot/agents}"

# --- the names THIS toolkit manages (purge by name only — never blanket-delete the dirs) -------------------
ALL_SKILLS="legacy-crawl-capture react-replica-kit parity-verify springboot-target-kit"
ALL_AGENTS="modernize-flow.agent.md jsp2react.agent.md"
RETIRED_AGENTS="jsp2react-analyzer.agent.md jsp2react-builder.agent.md"   # v2 — always purged

if [ "$MODE" = "full" ]; then
  WANT_SKILLS="legacy-crawl-capture react-replica-kit parity-verify springboot-target-kit"
  WANT_AGENT="modernize-flow.agent.md"
else
  WANT_SKILLS="legacy-crawl-capture react-replica-kit parity-verify"
  WANT_AGENT="jsp2react.agent.md"
fi

echo ">> modernization toolkit install — MODE=$MODE"
echo "   skills -> $SKILLS_DST"
echo "   agents -> $AGENTS_DST"
mkdir -p "$SKILLS_DST" "$AGENTS_DST"

echo ">> purging this toolkit's managed skills + agents (clean install)"
for s in $ALL_SKILLS; do
  if [ -d "$SKILLS_DST/$s" ]; then rm -rf "${SKILLS_DST:?}/$s" && echo "   removed skill  $s"; fi
done
for a in $ALL_AGENTS $RETIRED_AGENTS; do
  if [ -f "$AGENTS_DST/$a" ]; then rm -f "$AGENTS_DST/$a" && echo "   removed agent  $a"; fi
done

echo ">> installing the $MODE set"
for s in $WANT_SKILLS; do
  cp -r "$HERE/skills/$s" "$SKILLS_DST/" && echo "   installed skill  $s"
done
cp "$HERE/agents/$WANT_AGENT" "$AGENTS_DST/" && echo "   installed agent  $WANT_AGENT"

# sanity: the other mode's agent + (frontend) the backend skill must NOT be present
[ "$MODE" = "frontend" ] && { [ -d "$SKILLS_DST/springboot-target-kit" ] && { echo "   !! springboot-target-kit still present"; exit 1; } || true; }
OTHER_AGENT=$([ "$MODE" = "full" ] && echo jsp2react.agent.md || echo modernize-flow.agent.md)
[ -f "$AGENTS_DST/$OTHER_AGENT" ] && { echo "   !! other-mode agent $OTHER_AGENT still present"; exit 1; } || true

echo ">> installing pixel-diff deps (pixelmatch, pngjs) into parity-verify"
if command -v npm >/dev/null 2>&1; then
  ( cd "$SKILLS_DST/parity-verify" && npm install --silent --no-audit --no-fund ) || echo "   !! npm install failed — run it manually in $SKILLS_DST/parity-verify"
else
  echo "   !! npm not found — install Node.js, then: cd $SKILLS_DST/parity-verify && npm install"
fi

echo ">> prerequisite checks"
command -v node    >/dev/null 2>&1 && echo "   node:    $(node -v)"        || echo "   !! node missing (React app + pixel diff)"
command -v python3 >/dev/null 2>&1 && echo "   python3: $(python3 -V 2>&1)" || { command -v python >/dev/null 2>&1 && echo "   python:  $(python -V 2>&1)" || echo "   !! python missing (capture/extract/diff scripts)"; }
PYBIN="$(command -v python3 || command -v python || true)"
if [ -n "$PYBIN" ] && "$PYBIN" -c "import playwright" >/dev/null 2>&1; then
  echo "   playwright: ok"
  # the package being present does NOT mean a browser binary is installed (the exact pod failure) — verify one launches
  if "$PYBIN" -c "from playwright.sync_api import sync_playwright;
import sys
try:
    with sync_playwright() as p: p.chromium.launch(headless=True).close()
except Exception as e:
    sys.exit(1)" >/dev/null 2>&1; then
    echo "   browser:    chromium launches ok"
  else
    echo "   !! no launchable browser -> $PYBIN -m playwright install chromium   (Linux: also: $PYBIN -m playwright install-deps;"
    echo "      or capture with --channel chrome|msedge to use a system browser)"
  fi
else
  echo "   !! playwright missing -> pip install playwright && $PYBIN -m playwright install chromium"
fi
if [ "$MODE" = "full" ]; then
  command -v java  >/dev/null 2>&1 && echo "   java:    $(java -version 2>&1 | head -1)" || echo "   !! JDK missing (Spring Boot target — install a JDK 17+)"
  { command -v mvn >/dev/null 2>&1 && echo "   maven:   $(mvn -v 2>&1 | head -1)"; } || { command -v gradle >/dev/null 2>&1 && echo "   gradle:  present"; } || echo "   !! Maven/Gradle missing (Spring Boot build — or use the project's ./mvnw)"
fi

echo ""
echo "DONE ($MODE). Verify the engines, then start the agent:"
echo "  node   $SKILLS_DST/parity-verify/scripts/pixel_diff.js --self-check         # expect identical_diff_pixels: 0"
echo "  python $SKILLS_DST/legacy-crawl-capture/scripts/extract_jsp.py --self-check  # JSP source parser"
echo "  python $SKILLS_DST/react-replica-kit/scripts/extract_theme.py --self-check   # theme extractor"
[ "$MODE" = "full" ] && echo "  python $SKILLS_DST/springboot-target-kit/scripts/extract_backend.py --self-check  # stored-proc extractor"
echo "  In Copilot: run the **$( [ "$MODE" = "full" ] && echo modernize-flow || echo jsp2react )** agent with just the legacy URL + how to log in (+ a project.json)."
echo "  It bootstraps status.md itself (no hand-editing). Prompts: SETUP.md §6b."
