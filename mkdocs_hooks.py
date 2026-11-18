"""MkDocs hooks: put the package version in the site title and the home page heading, make the relative links in the
tutorial notebooks work on the site, and write the downloads and the files for language models.

The version is read from ``src/penicillium/_version.py``, so the title follows each release without editing.

mkdocs-jupyter renders notebooks with nbconvert, so their links are left as written. The notebooks link to other
pages as ``../page.md`` and to each other as ``NN_name.ipynb`` (links that work in Jupyter and on GitHub); on the
site, a notebook page lives one directory deeper, at ``tutorials/NN_name/``. This hook rewrites those links in the
rendered HTML.

After the build (``on_post_build``) the hook writes, from the sources of the same build:

* ``tutorials/penicillium_tutorials.zip``: every tutorial notebook (the "Download all" button of the overview);
* a Markdown copy of every page next to its HTML (``faults.md``, ``tutorials/01_first_batch.md``...): notebooks are
  converted to Markdown with their text outputs, and the API reference is rendered from the docstrings;
* ``llms.txt``: an index of those Markdown pages in the order of the navigation (https://llmstxt.org);
* ``llms-full.txt``: all of them in one file.
"""

import json
import re
import zipfile
from pathlib import Path

_VERSION = re.search(r'__version__ = "([^"]+)"', (Path(__file__).parent / "src/penicillium/_version.py").read_text())[1]
_LINK = re.compile(r'href="(?P<path>[^"#:]+?)\.(?P<ext>md|ipynb)(?P<anchor>#[^"]*)?"')

#: Navigation sections listed under "Optional" in llms.txt (useful, but not needed to use the package).
_OPTIONAL_SECTIONS = ("Validation", "Speed", "Related simulators", "Citing and references", "Licensing")

#: llms.txt summaries of pages whose first paragraph does not describe them.
_SUMMARIES = {
    "api.md": "Classes, functions and their options, from the docstrings.",
    "glossary.md": "Terms and abbreviations used in the documentation.",
    "dcs.md": "One batch in real time in a web-based operator console, and BatchSession to script it from Python.",
}

#: Longest text output of a notebook cell kept in its Markdown copy [lines].
_MAX_OUTPUT_LINES = 30


def _rewrite(match: re.Match) -> str:
    path, anchor = match["path"], match["anchor"] or ""
    if path.endswith("index"):
        path = path[: -len("index")]
    else:
        path += "/"
    return f'href="../{path}{anchor}"'


def on_config(config):
    config["site_name"] = f"{config['site_name']} {_VERSION}"
    return config


def on_page_markdown(markdown, page, config, files):
    if page.file.src_uri == "index.md":
        markdown = re.sub(r"\A# Penicillium$", f"# Penicillium {_VERSION}", markdown, count=1, flags=re.M)
    return markdown


def on_page_content(html, page, config, files):
    if not page.file.src_uri.endswith(".ipynb"):
        return html
    return _LINK.sub(_rewrite, html)


def on_post_build(config):
    site, docs = Path(config["site_dir"]), Path(config["docs_dir"])
    _write_tutorials_zip(docs, site)
    _write_llms_files(config, docs, site)


# ---------------------------------------------------------------------- tutorials zip


def _write_tutorials_zip(docs: Path, site: Path) -> None:
    """Every tutorial notebook in ``tutorials/penicillium_tutorials.zip`` (fixed timestamps: reproducible)."""
    out = site / "tutorials" / "penicillium_tutorials.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for nb in sorted((docs / "tutorials").glob("*.ipynb")):
            info = zipfile.ZipInfo(f"penicillium_tutorials/{nb.name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, nb.read_bytes())


# ---------------------------------------------------------------------- llms.txt and llms-full.txt


def _nav_pages(nav, section=None):
    """(section, title, source path) of every page of the navigation, in order."""
    for entry in nav:
        if isinstance(entry, str):
            yield section, None, entry
            continue
        for title, value in entry.items():
            if isinstance(value, list):
                yield from _nav_pages(value, title)
            elif not re.match(r"[a-z]+://", value):
                yield section or title, title, value


def _md_path(src: str) -> str:
    """Path of the Markdown copy of a page: ``faults.md``, ``tutorials/01_first_batch.md``."""
    return src[: -len(".ipynb")] + ".md" if src.endswith(".ipynb") else src


def _notebook_markdown(path: Path) -> str:
    """A notebook as Markdown: text cells, code cells and their text outputs (figures as a placeholder)."""
    nb = json.loads(path.read_text(encoding="utf-8"))
    parts = []
    for cell in nb["cells"]:
        source = "".join(cell["source"]).strip()
        if cell["cell_type"] == "markdown":
            parts.append(source)
            continue
        if cell["cell_type"] != "code" or not source:
            continue
        parts.append(f"```python\n{source}\n```")
        for out in cell.get("outputs", []):
            data = out.get("data", {})
            if out.get("output_type") == "stream":
                text = "".join(out["text"])
            elif "image/png" in data or "image/svg+xml" in data:
                parts.append("*[figure]*")
                continue
            elif "text/plain" in data:
                text = "".join(data["text/plain"])
            else:
                continue
            lines = text.rstrip().splitlines()
            if len(lines) > _MAX_OUTPUT_LINES:
                lines = [*lines[:_MAX_OUTPUT_LINES], f"... ({len(lines) - _MAX_OUTPUT_LINES} more lines)"]
            parts.append("Output:\n\n```text\n" + "\n".join(lines) + "\n```")
    text = "\n\n".join(parts) + "\n"
    return re.sub(r"\]\((\d{2}_[a-z0-9_]+)\.ipynb", r"](\1.md", text)  # links between notebooks


def _signature(fn) -> str:
    params = []
    for p in fn.parameters:
        if p.name in ("self", "cls"):
            continue
        text = p.name if p.annotation is None else f"{p.name}: {p.annotation}"
        if p.default is not None:
            text += f" = {p.default}"
        params.append(text)
    return f"({', '.join(params)})"


def _api_markdown(source: str, src_dir: Path) -> str:
    """The API reference: each ``::: dotted.path`` of ``api.md`` replaced by its docstrings (read statically)."""
    import griffe

    package = griffe.load("penicillium", search_paths=[str(src_dir)])

    def doc(obj) -> str:
        return obj.docstring.value.strip() if obj.docstring else ""

    def render(obj, path: str, level: int) -> list[str]:
        if obj.is_function:
            return [f"{'#' * level} `{path}{_signature(obj)}`", doc(obj)]
        if obj.is_class:
            init = obj.members.get("__init__")
            sig = _signature(init) if init is not None and not init.is_alias and init.is_function else ""
            out = [f"{'#' * level} class `{path}{sig}`", doc(obj)]
            for name, member in obj.members.items():
                if name.startswith("_") or member.is_alias or not member.docstring:
                    continue
                if member.is_function or member.is_attribute:
                    out += (
                        render(member, f"{path}.{name}", level + 1)
                        if member.is_function
                        else [f"{'#' * (level + 1)} `{path}.{name}`", doc(member)]
                    )
            return out
        out = [f"{'#' * level} `{path}`", doc(obj)]  # module
        for name, member in obj.members.items():
            if not name.startswith("_") and not member.is_alias and (member.is_class or member.is_function):
                out += render(member, f"{path}.{name}", level + 1)
        return out

    blocks = []
    for line in source.splitlines():
        match = re.match(r"::: (penicillium(?:\.\w+)*)\s*$", line)
        if not match:
            blocks.append(line)
            continue
        path = match[1]
        obj = package if path == "penicillium" else package[path.removeprefix("penicillium.")]
        blocks += render(obj, path, 2)
    return "\n\n".join(block for block in blocks if block.strip()) + "\n"


def _summary(markdown: str) -> str:
    """First sentence of the first paragraph of a page (for the llms.txt index)."""
    markdown = re.sub(r"^```.*?^```", "", markdown, flags=re.M | re.S)  # code blocks
    for block in re.split(r"\n\s*\n", markdown):
        block = block.strip()
        if not block or block[0] in "#!|<`:>-" or re.match(r"\d+\.\s|\*\s|\*\[figure|Output:", block):
            continue
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", " ".join(block.split())).replace("**", "")
        sentence = ""
        for part in re.split(r"(?<=[.!?])\s", text):  # whole sentences, at least ~30 characters
            sentence = f"{sentence} {part}".strip()
            if len(sentence) >= 30:
                break
        sentence = sentence.rstrip(":")
        return sentence if len(sentence) <= 200 else sentence[:197].rstrip() + "..."
    return ""


def _write_llms_files(config, docs: Path, site: Path) -> None:
    base = config["site_url"] or ""
    base = base if base.endswith("/") else base + "/"
    pages = []  # (section, title, Markdown path, Markdown)
    for section, title, src in _nav_pages(config["nav"]):
        path = docs / src
        if src.endswith(".ipynb"):
            text = _notebook_markdown(path)
        elif src == "api.md":
            text = _api_markdown(path.read_text(encoding="utf-8"), Path(__file__).parent / "src")
        else:
            text = path.read_text(encoding="utf-8")
            text = re.sub(r"\]\((\d{2}_[a-z0-9_]+)\.ipynb", r"](\1.md", text)
        if src == "index.md":
            text = re.sub(r"\A# Penicillium$", f"# Penicillium {_VERSION}", text, count=1, flags=re.M)
        md = _md_path(src)
        (site / md).parent.mkdir(parents=True, exist_ok=True)
        (site / md).write_text(text, encoding="utf-8")
        heading = re.search(r"^# (.+)$", text, flags=re.M)
        pages.append((section, title or (heading[1] if heading else md), md, text))

    index = [
        f"# Penicillium {_VERSION}",
        "",
        f"> {config['site_description']}",
        "",
        "Install with `pip install penicillium` (Python 3.10 or later). The main entry points are "
        "`penicillium.Simulator` (one batch), `penicillium.SimulationConfig` (switches, faults, batch length), "
        "`penicillium.FaultSpec` (fault onset, duration, magnitude), `penicillium.scenarios` (ready-made campaigns "
        "for fault detection, soft sensors and control) and `penicillium.envs` (Gymnasium environments). By default "
        "the simulator follows IndPenSim V2.01; every addition is an option. Each page below is plain Markdown; "
        f"[llms-full.txt]({base}llms-full.txt) holds all of them in one file.",
    ]
    sections: dict[str, list[str]] = {}
    for section, title, md, text in pages:
        name = "Optional" if section in _OPTIONAL_SECTIONS else section
        summary = _SUMMARIES.get(md) or _summary(text)
        sections.setdefault(name, []).append(f"- [{title}]({base}{md})" + (f": {summary}" if summary else ""))
    for name in sorted(sections, key=lambda n: n == "Optional"):  # Optional last, otherwise in navigation order
        index += ["", f"## {name}", "", *sections[name]]
    (site / "llms.txt").write_text("\n".join(index) + "\n", encoding="utf-8")

    full = [f"# Penicillium {_VERSION}: full documentation", "", f"> {config['site_description']}", ""]
    for _, _, md, text in pages:
        full += ["", "---", "", f"<!-- Source: {base}{md} -->", "", text.strip(), ""]
    (site / "llms-full.txt").write_text("\n".join(full), encoding="utf-8")
