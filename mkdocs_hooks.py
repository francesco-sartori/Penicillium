"""MkDocs hooks: put the package version in the site title and the home page heading, and make the relative links
in the tutorial notebooks work on the site.

The version is read from ``src/penicillium/_version.py``, so the title follows each release without editing.

mkdocs-jupyter renders notebooks with nbconvert, so their links are left as written. The notebooks link to other
pages as ``../page.md`` and to each other as ``NN_name.ipynb`` (links that work in Jupyter and on GitHub); on the
site, a notebook page lives one directory deeper, at ``tutorials/NN_name/``. This hook rewrites those links in the
rendered HTML.
"""

import re
from pathlib import Path

_VERSION = re.search(r'__version__ = "([^"]+)"', (Path(__file__).parent / "src/penicillium/_version.py").read_text())[1]
_LINK = re.compile(r'href="(?P<path>[^"#:]+?)\.(?P<ext>md|ipynb)(?P<anchor>#[^"]*)?"')


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
