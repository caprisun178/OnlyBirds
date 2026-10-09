"""Convert the MkDocs docs in docs/ into GitHub wiki pages.

    python scripts/build_wiki.py <out_dir> [--strict]

`docs/` + `mkdocs.yml` stay the single source of truth; this only renders
them into the shape a GitHub wiki expects, and
.github/workflows/publish-wiki.yml pushes the result to the repo's wiki.
Never edit the wiki directly: the next publish overwrites it.

What changes on the way:

- **Flat page names.** A wiki has no folders, and links name a page, not a
  file. Each page is named after its `mkdocs.yml` nav title
  ("Plan a trip" -> `Plan-a-trip.md`). Pages missing from the nav fall back
  to their first `# ` heading.
- **Links.** Relative `.md` links (`../ebird-api.md#rate-limits`) become
  wiki page links (`eBird-API#rate-limits`). Relative links to anything
  else point at the file on GitHub.
- **MkDocs-only syntax.** GitHub markdown has no admonitions, collapsible
  blocks or content tabs, so `!!! note` becomes a blockquote, `??? note`
  becomes `<details>`, and `=== "Tab"` becomes a bold label over its content.
- **Navigation.** `Home.md` and `_Sidebar.md` are generated from the nav, and
  `_Footer.md` says where to edit.

`--strict` exits non-zero on any relative `.md` link that doesn't resolve
to a page, so CI catches a broken wiki link the same way
`mkdocs build --strict` catches a broken site link.
"""

from __future__ import annotations

import os
import posixpath
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
REPO = os.environ.get("GITHUB_REPOSITORY", "caprisun178/OnlyBirds")
BRANCH = "main"

FENCE_RE = re.compile(r"^\s*(```|~~~)")
QUOTED = r'"((?:[^"\\]|\\.)*)"'  # a "title", allowing \" escapes inside it
ADMONITION_RE = re.compile(r'^(\s*)(!!!|\?\?\?\+?)\s+([\w-]+)(?:\s+' + QUOTED + r')?\s*$')
TAB_RE = re.compile(r'^(\s*)===\s+' + QUOTED + r'\s*$')
LINK_RE = re.compile(r"(\]\()([^)\s]+)(\))")


# ---- Page naming ------------------------------------------------------------

def walk_nav(nav, section=None):
    """Yield (section, title, docs-relative path) for every page in the nav."""
    for item in nav:
        if isinstance(item, str):  # bare `- page.md` entry, no title
            yield section, None, item
            continue
        for title, value in item.items():
            if isinstance(value, str):
                yield section, title, value
            else:
                yield from walk_nav(value, title)


def wiki_name(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")


def first_heading(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").capitalize()


def build_page_map(nav):
    """docs-relative path -> (wiki page name, display title), plus the nav
    as [(section, [(title, page name), ...])] for the sidebar."""
    pages: dict[str, tuple[str, str]] = {}
    used: set[str] = set()
    sections: list[tuple[str | None, list[tuple[str, str]]]] = []

    def claim(rel: str, title: str, section: str | None) -> str:
        name = wiki_name(title)
        if name.lower() in used or name.lower() in ("home", "_sidebar", "_footer"):
            name = wiki_name(f"{section or 'Docs'} {title}")
        used.add(name.lower())
        pages[rel] = (name, title)
        return name

    for section, title, rel in walk_nav(nav):
        title = title or first_heading(DOCS / rel)
        name = claim(rel, title, section)
        if not sections or sections[-1][0] != section:
            sections.append((section, []))
        sections[-1][1].append((title, name))

    unlisted = []
    for path in sorted(DOCS.rglob("*.md")):
        rel = path.relative_to(DOCS).as_posix()
        if rel not in pages:
            title = first_heading(path)
            unlisted.append((title, claim(rel, title, "More")))
    if unlisted:
        sections.append(("More", unlisted))
    return pages, sections


# ---- Block syntax -------------------------------------------------------------

def take_indented(lines, i, indent):
    """Collect the indented body that follows an admonition/tab line."""
    pad = " " * (indent + 4)
    body = []
    while i < len(lines) and (not lines[i].strip() or lines[i].startswith(pad)):
        body.append(lines[i][len(pad):] if lines[i].strip() else "")
        i += 1
    while body and not body[-1]:  # trailing blank lines belong to the outer text
        body.pop()
        i -= 1
    while body and not body[0]:
        body.pop(0)
    return body, i


def convert_blocks(lines):
    out, i, fence = [], 0, None
    while i < len(lines):
        line = lines[i]
        fence_match = FENCE_RE.match(line)
        if fence:
            out.append(line)
            if fence_match and fence_match.group(1) == fence:
                fence = None
            i += 1
            continue
        if fence_match:
            fence = fence_match.group(1)
            out.append(line)
            i += 1
            continue

        adm = ADMONITION_RE.match(line)
        tab = TAB_RE.match(line)
        if adm:
            indent = len(adm.group(1))
            kind = adm.group(3)
            title = None if adm.group(4) is None else adm.group(4).replace('\\"', '"')
            body, i = take_indented(lines, i + 1, indent)
            body = convert_blocks(body)
            pad = " " * indent
            label = kind.capitalize() if title is None else (title or kind.capitalize())
            if adm.group(2).startswith("???"):
                opened = " open" if adm.group(2).endswith("+") else ""
                out.append(f"{pad}<details{opened}><summary>{label}</summary>")
                out.append("")
                out.extend(f"{pad}{b}" if b else "" for b in body)
                out.append("")
                out.append(f"{pad}</details>")
            else:
                heading = f"**{kind.capitalize()}: {title}**" if title else f"**{label}**"
                out.append(f"{pad}> {heading}")
                out.append(f"{pad}>")
                out.extend(f"{pad}> {b}" if b else f"{pad}>" for b in body)
            continue
        if tab:
            indent = len(tab.group(1))
            body, i = take_indented(lines, i + 1, indent)
            pad = " " * indent
            tab_title = tab.group(2).replace('\\"', '"')
            out.append(f"{pad}**{tab_title}**")
            out.append("")
            out.extend(f"{pad}{b}" if b else "" for b in convert_blocks(body))
            continue

        out.append(line)
        i += 1
    return out


# ---- Links ----------------------------------------------------------------------

def rewrite_links(text: str, page_rel: str, pages, broken: list[str]) -> str:
    page_dir = posixpath.dirname(page_rel)

    def fix(m: re.Match) -> str:
        target = m.group(2)
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("#"):
            return m.group(0)  # external URL, mailto:, or same-page anchor
        path, _, anchor = target.partition("#")
        resolved = posixpath.normpath(posixpath.join(page_dir, path))
        if resolved.endswith("/") or resolved in (".", ""):
            resolved = posixpath.join(resolved, "index.md")
        if resolved in pages:
            name = pages[resolved][0]
            return f"{m.group(1)}{name}{'#' + anchor if anchor else ''}{m.group(3)}"
        if path.endswith(".md"):
            broken.append(f"{page_rel}: {target}")
            return m.group(0)
        repo_path = posixpath.normpath(posixpath.join("docs", resolved))
        return f"{m.group(1)}https://github.com/{REPO}/blob/{BRANCH}/{repo_path}{'#' + anchor if anchor else ''}{m.group(3)}"

    # Leave code untouched: only rewrite outside fenced blocks and inline code.
    out, fence = [], None
    for line in text.split("\n"):
        fence_match = FENCE_RE.match(line)
        if fence:
            if fence_match and fence_match.group(1) == fence:
                fence = None
            out.append(line)
            continue
        if fence_match:
            fence = fence_match.group(1)
            out.append(line)
            continue
        parts = re.split(r"(`[^`]*`)", line)
        out.append("".join(p if p.startswith("`") else LINK_RE.sub(fix, p) for p in parts))
    return "\n".join(out)


# ---- Main -------------------------------------------------------------------------

def nav_markdown(sections) -> list[str]:
    lines = []
    for n, (section, entries) in enumerate(sections):
        if section:
            lines += ["", f"**{section}**", ""]
        elif n:  # top-level pages after a section: break out of it visibly
            lines += ["", "---", ""]
        lines += [f"- [{title}]({name})" for title, name in entries]
    return lines


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    out_dir = Path(args[0])
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.md"):
        old.unlink()

    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    pages, sections = build_page_map(config["nav"])

    broken: list[str] = []
    for rel, (name, _title) in pages.items():
        text = (DOCS / rel).read_text(encoding="utf-8")
        text = "\n".join(convert_blocks(text.split("\n")))
        text = rewrite_links(text, rel, pages, broken)
        (out_dir / f"{name}.md").write_text(text, encoding="utf-8")

    site = config.get("site_name", "Docs")
    description = (config.get("site_description") or "").strip()
    home = [f"# {site}", "", description, "", "Developer documentation, mirrored from `docs/` in the repo."]
    (out_dir / "Home.md").write_text("\n".join(home + nav_markdown(sections)) + "\n", encoding="utf-8")
    (out_dir / "_Sidebar.md").write_text(
        "\n".join([f"**[{site}](Home)**"] + nav_markdown(sections)) + "\n", encoding="utf-8"
    )
    (out_dir / "_Footer.md").write_text(
        f"Generated from [`docs/`](https://github.com/{REPO}/tree/{BRANCH}/docs). "
        "Edit the Markdown there, not here: this wiki is overwritten on every publish.\n",
        encoding="utf-8",
    )

    print(f"Wrote {len(pages)} pages + Home, _Sidebar, _Footer to {out_dir}")
    for b in broken:
        print(f"broken link: {b}", file=sys.stderr)
    return 1 if strict and broken else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
