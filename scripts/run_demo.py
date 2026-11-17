#!/usr/bin/env python3
"""Headlessly run a single-file HTML demo and report what broke.

    python3 run_demo.py demo.html [--probe "typeof simulate === 'function'"] [--shot out.png]

Port of LearnHarness's run_demo: loads the page in headless Chromium, lets it
settle, and reports uncaught errors, unhandled rejections, console.error calls,
failed resource loads, and the value of an optional probe expression. Exit 0 and
"PASSED" only when nothing went wrong. --shot also saves a screenshot so the
builder can LOOK at the demo.
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CANDIDATES = [
    os.environ.get("TUTOR_CHROME", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    *sorted(glob.glob(os.path.expanduser(
        "~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell")), reverse=True),
    *sorted(glob.glob(os.path.expanduser(
        "~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/*.app/Contents/MacOS/*")), reverse=True),
    *sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell")), reverse=True),
    shutil.which("chromium") or "", shutil.which("google-chrome") or "", shutil.which("chromium-browser") or "",
]

PRELUDE = """<script>
window.__tutorErrors = [];
window.addEventListener('error', function (e) {
  if (e.target && e.target !== window && (e.target.src || e.target.href)) {
    __tutorErrors.push('failed to load: ' + (e.target.src || e.target.href));
  } else {
    __tutorErrors.push('uncaught: ' + (e.message || e.type) + (e.filename ? ' @' + e.filename.split('/').pop() + ':' + e.lineno : ''));
  }
}, true);
window.addEventListener('unhandledrejection', function (e) {
  __tutorErrors.push('unhandled rejection: ' + ((e.reason && e.reason.message) || e.reason));
});
(function () { var ce = console.error; console.error = function () {
  __tutorErrors.push('console.error: ' + Array.prototype.map.call(arguments, String).join(' '));
  return ce.apply(console, arguments); }; })();
</script>"""

REPORTER = """<script>
setTimeout(function () {
  var r = { errors: window.__tutorErrors, title: document.title, bodyText: (document.body && document.body.innerText || '').slice(0, 300) };
  try { r.probe = String(eval(%s)); } catch (e) { r.probeError = String(e); }
  var el = document.createElement('script'); el.type = 'application/json'; el.id = '__tutor_report';
  el.textContent = JSON.stringify(r); document.documentElement.appendChild(el);
}, %d);
</script>"""


def find_chrome() -> str | None:
    for c in CANDIDATES:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return None


def instrument(source: str, probe: str | None, settle_ms: int) -> str:
    rep = REPORTER % (json.dumps(probe or "undefined"), settle_ms)
    if re.search(r"<head[^>]*>", source, re.I):
        source = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + PRELUDE, source, count=1, flags=re.I)
    else:
        source = PRELUDE + source
    if re.search(r"</body>", source, re.I):
        return re.sub(r"(</body>)", lambda m: rep + m.group(1), source, count=1, flags=re.I)
    return source + rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("--probe")
    ap.add_argument("--shot")
    ap.add_argument("--settle", type=int, default=2000, help="ms to let the page run before reporting")
    ap.add_argument("--size", default="1100,800")
    args = ap.parse_args()

    chrome = find_chrome()
    if not chrome:
        print("HEADLESS UNAVAILABLE: no Chrome/Chromium found. Install Chrome, or `npx playwright install chromium-headless-shell`, "
              "or set TUTOR_CHROME to a Chromium binary.")
        sys.exit(2)
    src = Path(args.html).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "demo.html"
        page.write_text(instrument(src, args.probe, args.settle), encoding="utf-8")
        base = [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                "--allow-file-access-from-files", f"--user-data-dir={tmp}/profile",
                f"--virtual-time-budget={args.settle + 1500}", f"--window-size={args.size}"]
        try:
            res = subprocess.run([*base, "--dump-dom", page.as_uri()], capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            print("FAILED: the page did not finish within 60s (infinite loop or blocking work at load?).")
            sys.exit(1)
        m = re.search(r'<script type="application/json" id="__tutor_report">(.*?)</script>', res.stdout, re.S)
        if not m:
            print("FAILED: no report from the page. It crashed or hung before settling.")
            print((res.stderr or "")[-1500:])
            sys.exit(1)
        report = json.loads(html.unescape(m.group(1)))
        if args.shot:
            shot = Path(args.shot).resolve()
            subprocess.run([*base, f"--screenshot={shot}", page.as_uri()], capture_output=True, text=True, timeout=60)
            print(f"screenshot: {shot}" if shot.exists() else "screenshot: failed")

    problems = list(report.get("errors") or [])
    if report.get("probeError"):
        problems.append(f"probe threw: {report['probeError']}")
    if args.probe:
        print(f"probe {args.probe!r} → {report.get('probe')}")
    if problems:
        print("FAILED:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("PASSED: no errors after settling." + (" Check the probe value above." if args.probe else ""))


if __name__ == "__main__":
    main()
