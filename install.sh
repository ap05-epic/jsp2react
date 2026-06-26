#!/usr/bin/env bash
# install.sh — one command to set up jsp2react during the manual phase.
#
# Places the skills + agents into the Copilot folders (~/.copilot/skills and ~/.copilot/agents),
# installs the pixel-diff deps, and checks the runtime prerequisites. Run from the cloned repo root:
#
#   bash install.sh
#
# Override targets if your pod differs:  COPILOT_SKILLS_DIR=… COPILOT_AGENTS_DIR=… bash install.sh
# (Once DigitCode packaging is ready, `dc agent install jsp2react` replaces this script.)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

SKILLS_DST="${COPILOT_SKILLS_DIR:-$HOME/.copilot/skills}"
AGENTS_DST="${COPILOT_AGENTS_DIR:-$HOME/.copilot/agents}"

echo ">> jsp2react install"
echo "   skills -> $SKILLS_DST"
echo "   agents -> $AGENTS_DST"
mkdir -p "$SKILLS_DST" "$AGENTS_DST"

cp -r "$HERE"/skills/*            "$SKILLS_DST"/
cp    "$HERE"/agents/*.agent.md   "$AGENTS_DST"/

echo ">> installing pixel-diff deps (pixelmatch, pngjs) into the parity-verify skill"
if command -v npm >/dev/null 2>&1; then
  ( cd "$SKILLS_DST/parity-verify" && npm install --silent --no-audit --no-fund )
else
  echo "   !! npm not found — install Node.js, then: cd $SKILLS_DST/parity-verify && npm install"
fi

echo ">> prerequisite checks"
command -v node    >/dev/null 2>&1 && echo "   node:    $(node -v)"        || echo "   !! node missing (needed for the React app + pixel diff)"
command -v python3 >/dev/null 2>&1 && echo "   python3: $(python3 -V 2>&1)" || echo "   !! python3 missing (needed for capture/diff scripts)"
if python3 -c "import playwright" >/dev/null 2>&1; then
  echo "   playwright: ok"
else
  echo "   !! playwright missing -> pip install playwright && playwright install chromium"
fi

echo ""
echo "DONE. Verify the pixel engine, then start:"
echo "  node $SKILLS_DST/parity-verify/scripts/pixel_diff.js --self-check    # expect identical_diff_pixels: 0"
echo "  cp $HERE/templates/STATUS.md <your-run-folder>/   # then fill in sections 1-3"
echo "  In Copilot: run the jsp2react-analyzer agent (prompts in SETUP.md section 6b)."
