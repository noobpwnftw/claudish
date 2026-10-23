"""Build the static demo: the browser demo, with the model running in the page (no inference server).

python scripts/build_static_demo.py [--out dist/demo]
python scripts/build_static_demo.py --site [--out dist/site]   # the home page, with the demo in demo/

The output is plain files for any static host (for example GitHub Pages). The templates come from
claudish/modes.py, so the page and the service never drift apart.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from claudish import modes  # noqa: E402

# Pinned like scripts/download_model.py's "small" preset (the tested default model).
MODEL_URL = ("https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/"
             "9217f5db79a29953eb74d5343926648285ec7e67/qwen2.5-0.5b-instruct-q4_k_m.gguf")
MODEL_BYTES = 491400032
CSP = ("default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'wasm-unsafe-eval'; "
       "worker-src 'self' blob: https://cdn.jsdelivr.net; connect-src 'self' https:; style-src 'self'; "
       "img-src 'self' data:; base-uri 'none'; form-action 'none'")
REPO = "https://github.com/noobpwnftw/claudish"
FILES = ["index.html", "demo.css", "demo.js", "theme.js", "browser.js", "coi-sw.js", "favicon.png", "favicon-dark.png"]


def build(out):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    web = ROOT / "claudish" / "web"
    for name in FILES:
        shutil.copy(web / name, out / name)
    page = (out / "index.html").read_text(encoding="utf-8")
    page = re.sub(r'(href|src)="/(?!/)', r'\1="', page)  # relative paths: hosts may serve from a subpath
    head = ('  <meta name="claudish-backend" content="browser">\n'
            '  <meta name="claudish-model" content="Qwen2.5 0.5B (%d MB)">\n'
            '  <meta http-equiv="Content-Security-Policy" content="%s">\n' % (MODEL_BYTES // 1_000_000, CSP))
    page = page.replace('  <meta charset="utf-8">\n', '  <meta charset="utf-8">\n' + head, 1)
    # As the project home page, point visitors to the source and the install instructions.
    page = page.replace('<footer class="page-footer">', '<footer class="page-footer"><a href="%s">Source, install, and docs on GitHub ↗</a>' % REPO, 1)
    (out / "index.html").write_text(page, encoding="utf-8")
    templates = {"model_url": MODEL_URL, "model_bytes": MODEL_BYTES, "max_tokens": 64,
                 "modes": {name: {"system": spec["system"], "examples": spec["examples"],
                                  "max_tokens": spec["max_tokens"], "frame": spec.get("frame")}
                           for name, spec in modes.defaults().items()}}
    (out / "templates.json").write_text(json.dumps(templates, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


SITE_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'none'; base-uri 'none'; form-action 'none'")


def build_site(out):
    """The home page (site/) at the root and the demo in demo/. The page shares the demo's color tokens."""
    out = Path(out)
    build(out / "demo")
    site, web = ROOT / "site", ROOT / "claudish" / "web"
    css = (web / "demo.css").read_text(encoding="utf-8")
    tokens = [re.search(r":root\{[^}]*\}", css).group(0), re.search(r':root\[data-theme="dark"\]\{[^}]*\}', css).group(0)]
    (out / "site.css").write_text("\n".join(tokens) + "\n" + (site / "site.css").read_text(encoding="utf-8"),
                                  encoding="utf-8")
    shutil.copy(site / "site.js", out / "site.js")
    for name in ("favicon.png", "favicon-dark.png"):
        shutil.copy(site / name, out / name)
    shutil.copy(web / "theme.js", out / "theme.js")
    page = (site / "index.html").read_text(encoding="utf-8")
    page = page.replace('  <meta charset="utf-8">\n', '  <meta charset="utf-8">\n'
                        '  <meta http-equiv="Content-Security-Policy" content="%s">\n' % SITE_CSP, 1)
    (out / "index.html").write_text(page, encoding="utf-8")
    demo = (out / "demo" / "index.html").read_text(encoding="utf-8")
    demo = demo.replace('<a class="wordmark" href=""', '<a class="wordmark" href="../"', 1)  # back to the home page
    (out / "demo" / "index.html").write_text(demo, encoding="utf-8")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", action="store_true", help="Build the home page, with the demo in demo/")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.site:
        print("Built", build_site(args.out or ROOT / "dist" / "site"))
    else:
        print("Built", build(args.out or ROOT / "dist" / "demo"))


if __name__ == "__main__":
    main()
