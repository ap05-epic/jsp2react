#!/usr/bin/env bash
# scaffold_app.sh — create the fresh Vite + React + TS replica app, wired for MSW fixtures.
#
# Produces a clean app whose ONLY job is to render 1:1 legacy replicas from captured fixtures.
# No component library (a library would restyle and break "no new artifacts"). Plain CSS Modules.
#
# Usage:  bash scaffold_app.sh <target-dir>
# Idempotent-ish: refuses to overwrite a non-empty existing target.
set -euo pipefail

TARGET="${1:-}"
[ -z "$TARGET" ] && { echo "usage: scaffold_app.sh <target-dir>"; exit 1; }
if [ -e "$TARGET" ] && [ -n "$(ls -A "$TARGET" 2>/dev/null || true)" ]; then
  echo "refusing: '$TARGET' exists and is not empty"; exit 1
fi

echo ">> creating Vite React-TS app at $TARGET"
npm create vite@latest "$TARGET" -- --template react-ts
cd "$TARGET"

echo ">> installing deps (react app + MSW + pixel-diff tooling)"
npm install
npm i -D msw pixelmatch pngjs

echo ">> initializing MSW service worker into public/"
npx msw init public/ --save

echo ">> writing mock wiring (src/mocks/*)"
mkdir -p src/mocks src/screens
cat > src/mocks/handlers.ts <<'EOF'
// Aggregates every per-screen handler set. capture_fixtures.py writes src/mocks/<screenId>/handlers.ts
// (+ fixtures.json). They are collected here via Vite's import.meta.glob — no manual registration.
const mods = import.meta.glob('./*/handlers.ts', { eager: true }) as Record<string, { handlers?: unknown[] }>
export const handlers = Object.values(mods).flatMap(m => m.handlers ?? [])
EOF

cat > src/mocks/browser.ts <<'EOF'
import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'
export const worker = setupWorker(...handlers)
EOF

echo ">> wiring MSW bootstrap into src/main.tsx (MSW on by default; set VITE_MSW=off to hit real backend)"
cat > src/main.tsx <<'EOF'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './index.css'

async function enableMocks() {
  if (import.meta.env.VITE_MSW === 'off') return
  const { worker } = await import('./mocks/browser')
  // onUnhandledRequest:'bypass' so un-fixtured calls fall through instead of erroring.
  await worker.start({ onUnhandledRequest: 'bypass' })
}

enableMocks().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode><App /></StrictMode>,
  )
})
EOF

echo ">> seeding a minimal router-free App shell (replace as screens are built)"
cat > src/App.tsx <<'EOF'
// Minimal shell. The builder adds one screen per iteration under src/screens/<Name>/ and routes to it.
// Use the URL hash (e.g. #/f010) or a router of your choice; keep routes matching STATUS.md IDs.
export default function App() {
  return (
    <div id="app-root">
      <p>jsp2react replica shell. Build screens under <code>src/screens/</code> and route by STATUS.md ID.</p>
    </div>
  )
}
EOF

echo ""
echo "DONE. Next:"
echo "  1) per screen, capture fixtures:  python <…>/legacy-crawl-capture/scripts/capture_fixtures.py \\"
echo "        --network work/screenshots/<id>.network.json --out src/mocks/<id>"
echo "  2) build the screen under src/screens/<Name>/ (see react-replica-kit references)"
echo "  3) npm run dev   # serves on http://localhost:5173 with MSW fixtures"
