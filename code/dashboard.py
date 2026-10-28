"""Draw the state of every DANDI cache as one SVG table, with a TSV of the same numbers.

Standard library only, so the workflow runs it with the runner's own `python3`. Everything comes
from the GitHub API and raw file URLs; nothing is cloned.

A cache is any repository of the organization with a `cache.toml` at the root of its default branch,
other than the template. For each one:

- `sourcedata`: the caches its `cache.toml` declares as `[[inputs]]`. A cache with none reads the DANDI
  archive itself.
- `used_by`: the caches that declare it as an input.
- `derivatives_data`: the bytes of data under `derivatives/` on the `derivatives` branch. A Zarr
  store counts the length of its array, which is the data it holds.
- `derivatives_files`: the bytes of the files under `derivatives/`, as they sit on disk in a clone.
  This is the data plus the newlines padding each store's last chunk file to the full chunk size,
  which can make a store of a few kilobytes take tens of megabytes.
- `dist`: the bytes of the whole `dist` branch, which holds only what is published.
- `updated`: when the `derivatives` branch last moved. The drawing colors it by its age when drawn, from
  green when just updated through amber to red once it is `STALE`.
- `progress`: the last `Progress: <recorded> of <candidates> candidates recorded` line that
  `run_incremental_update` writes to the run logs under `logs/` on the `derivatives` branch.
  A cache whose runs do not write one (an older library, or a cache that selects its own batch)
  shows a dash.
- `end_to_end`: how much of the whole chain from the archive the cache has covered: its own fraction
  times that of each cache upstream of it that reports one, so a cache done with its sourcedata while
  that sourcedata is half done stands at half. Given only when it differs from the cache's own.

Usage: `python3 code/dashboard.py --output <directory>`, which writes `dashboard.svg` and `dashboard.tsv`
(lists joined by commas), or `python3 code/dashboard.py --mermaid` for the README's diagram of the inputs.

The rows are ordered by their sourcedata: by the longest chain of inputs from the archive, then by where
a cache's inputs sit, which is about how the diagram reads, left to right and then top to bottom.
`GITHUB_TOKEN`, when set, is sent with every API request.
"""

import argparse
import base64
import csv
import datetime
import json
import math
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape

import tomllib

ORGANIZATION = "dandi-cache"
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

#: The progress line `dandi_cache_utils.run_incremental_update` logs at the end of a run.
PROGRESS = re.compile(r"Progress: ([\d,]+) of ([\d,]+) candidates recorded")
#: A run log, `logs/<operation>_<UTC timestamp>.log`; the timestamp sorts as text.
RUN_LOG = re.compile(r"^logs/[a-z_]+_\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z\.log$")
#: The array metadata of a Zarr store under `derivatives/`, whose `shape` is the bytes of data it holds.
STORE_ARRAY = re.compile(r"^(derivatives/.+\.zarr)/stream/zarr\.json$")
#: How many of the newest run logs to search for a progress line before giving up.
LOGS_TO_SEARCH = 5
#: Seconds to wait before each retry of a request GitHub failed to answer; one 502 used to end a run.
RETRY_DELAYS = (5, 20, 60)


def request(url: str, /) -> urllib.request.Request:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "dandi-cache-dashboard"}
    if url.startswith(API) and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    return urllib.request.Request(url, headers=headers)


def open_url(url: str, /):
    """Open a URL, retrying a server error, a rate limit or a dropped connection a few times."""
    for delay in (*RETRY_DELAYS, None):
        try:
            return urllib.request.urlopen(request(url), timeout=60)
        except urllib.error.HTTPError as error:
            if delay is None or not (error.code >= 500 or error.code == 429):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if delay is None:
                raise
        print(f"Retrying {url} in {delay} s.", file=sys.stderr)
        time.sleep(delay)


def get(path: str, /) -> dict | list | None:
    """One API response, or `None` for a 404 (a branch or file that does not exist)."""
    try:
        with open_url(f"{API}{path}") as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def get_all(path: str, /) -> list:
    """Every page of a listing."""
    items, url = [], f"{API}{path}"
    while url:
        with open_url(url) as response:
            items += json.load(response)
            links = response.headers.get("Link", "")
        url = next((part.split(";")[0].strip("<> ") for part in links.split(",") if 'rel="next"' in part), None)
    return items


def get_text(url: str, /) -> str:
    with open_url(url) as response:
        return response.read().decode("utf-8", errors="replace")


def tree(repo: str, sha: str, /) -> tuple[list[dict], bool]:
    """Every blob of a commit's tree, and whether GitHub truncated the listing."""
    listing = get(f"/repos/{ORGANIZATION}/{repo}/git/trees/{sha}?recursive=1") or {"tree": []}
    return [entry for entry in listing["tree"] if entry["type"] == "blob"], listing.get("truncated", False)


def branch(repo: str, name: str, /) -> dict | None:
    return get(f"/repos/{ORGANIZATION}/{repo}/branches/{urllib.parse.quote(name)}")


def inputs(repo: str, /) -> list[str] | None:
    """The caches a repository's `cache.toml` declares as inputs, or `None` if it has no `cache.toml`."""
    found = get(f"/repos/{ORGANIZATION}/{repo}/contents/cache.toml")
    if found is None:
        return None
    configuration = tomllib.loads(base64.b64decode(found["content"]).decode("utf-8"))
    return [entry["name"] for entry in configuration.get("inputs", [])]


def caches() -> dict[str, list[str]]:
    """Every live repository of the organization with a `cache.toml`, except the template, with its inputs."""
    found = {}
    for repo in get_all(f"/orgs/{ORGANIZATION}/repos?per_page=100&type=public"):
        if repo["archived"] or repo["is_template"]:
            continue
        declared = inputs(repo["name"])
        if declared is not None:
            found[repo["name"]] = declared
    return dict(sorted(found.items()))


def progress(repo: str, sha: str, blobs: list[dict], /) -> tuple[int, int] | None:
    """`(recorded, candidates)` from the newest run log that says, or `None`."""
    logs = sorted((entry["path"] for entry in blobs if RUN_LOG.match(entry["path"])), key=lambda path: path[-24:])
    for path in reversed(logs[-LOGS_TO_SEARCH:]):
        matches = PROGRESS.findall(get_text(f"{RAW}/{ORGANIZATION}/{repo}/{sha}/{path}"))
        if matches:
            recorded, candidates = matches[-1]
            return int(recorded.replace(",", "")), int(candidates.replace(",", ""))
    return None


def derivatives_bytes(repo: str, sha: str, blobs: list[dict], /) -> tuple[int, int]:
    """The bytes of data under `derivatives/`, counting each Zarr store by its array's length, and of its files."""
    stores = [match[1] for entry in blobs if (match := STORE_ARRAY.match(entry["path"]))]
    total = sum(
        json.loads(get_text(f"{RAW}/{ORGANIZATION}/{repo}/{sha}/{store}/stream/zarr.json"))["shape"][0]
        for store in stores
    )
    chunks = tuple(f"{store}/stream/c/" for store in stores)
    files = [entry for entry in blobs if entry["path"].startswith("derivatives/")]
    data = total + sum(entry["size"] for entry in files if not entry["path"].startswith(chunks))
    return data, sum(entry["size"] for entry in files)


def describe(repo: str, sourcedata: list[str], used_by: list[str], /) -> dict:
    """One row of the table."""
    row = {
        "cache": repo,
        "sourcedata": sourcedata,
        "used_by": used_by,
        "derivatives_data": None,
        "derivatives_files": None,
        "dist_bytes": None,
        "updated": None,
        "recorded": None,
        "candidates": None,
        "truncated": False,
    }
    derivatives = branch(repo, "derivatives")
    if derivatives is not None:
        sha = derivatives["commit"]["sha"]
        row["updated"] = derivatives["commit"]["commit"]["committer"]["date"]
        blobs, truncated = tree(repo, sha)
        row["derivatives_data"], row["derivatives_files"] = derivatives_bytes(repo, sha, blobs)
        row["truncated"] |= truncated
        found = progress(repo, sha, blobs)
        if found is not None:
            row["recorded"], row["candidates"] = found
    dist = branch(repo, "dist")
    if dist is not None:
        blobs, truncated = tree(repo, dist["commit"]["sha"])
        row["dist_bytes"] = sum(entry["size"] for entry in blobs)
        row["truncated"] |= truncated
    return row


# ------------------------------------------------------------------------------------------------
# Drawing
# ------------------------------------------------------------------------------------------------

WIDTH = 1450
#: A row's height when each of its cells is one line, and what each further line of a list adds.
ROW, LINE = 30, 16
TOP = 44
#: Column anchors: the names from the left, the other columns and their titles centered.
NAME_X, SOURCE_X, USED_BY_X = 24, 300, 530
DATA_X, FILES_X, DIST_X, UPDATED_X = 830, 940, 1050, 1180
#: The bar from its left edge and the percentage right-aligned, under a title centered on both.
BAR_X, BAR_WIDTH, PERCENT_X = 1284, 80, 1426
PROCESSED_X = (BAR_X + PERCENT_X) // 2
#: What reads the DANDI archive itself rather than another cache.
ARCHIVE = "DANDI archive"
#: How old a cache's last update is when its date is drawn fully red; a newer one runs through amber to green.
STALE = datetime.timedelta(days=3)
#: The OKLCH hues of a date just updated and of one `STALE` or older, and the lightness and chroma it is drawn
#: with on each surface. One lightness for every hue keeps every age as legible: 4.5:1 or more against the light
#: surface and 6.5:1 against the dark.
FRESH_HUE, STALE_HUE = 145, 29
AGE_LIGHT, AGE_DARK = (0.53, 0.15), (0.72, 0.17)

STYLE = """
  svg { --surface: #fcfcfb; --text-primary: #0b0b0b; --text-secondary: #52514e; --muted: #898781;
        --grid: #e1e0d9; --track: #ecebe6; --series: #2a78d6;
        --whole: #eb6834; }
  @media (prefers-color-scheme: dark) {
    svg { --surface: #1a1a19; --text-primary: #f0efec; --text-secondary: #c3c2b7; --muted: #898781;
          --grid: #2c2c2a; --track: #2c2c2a; --series: #3987e5;
          --whole: #d95926; }
  }
  text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
         fill: var(--text-primary); font-size: 13px; }
  .surface { fill: var(--surface); }
  .updated { fill: var(--text-secondary); font-size: 12px; }
  .list { fill: var(--text-secondary); font-size: 12px; }
  .head { fill: var(--muted); font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
  .num { font-variant-numeric: tabular-nums; }
  .none { fill: var(--muted); }
  .rule { stroke: var(--grid); stroke-width: 1; }
  .track { fill: var(--track); }
  .bar { fill: var(--series); }
  .whole { fill: var(--whole); }
  .age { fill: var(--age); font-weight: 600; }
  @media (prefers-color-scheme: dark) { .age { fill: var(--age-dark); } }
"""


def human_size(size: int | None, /) -> str:
    """Write a size in decimal units (1 kB = 1000 B), with three significant figures."""
    if size is None:
        return "—"
    value = float(size)
    for unit in ("B", "kB", "MB", "GB", "TB"):
        rounded = float(f"{value:.3g}")
        if rounded < 1000 or unit == "TB":
            break
        value /= 1000
    decimals = 0 if unit == "B" or rounded >= 100 else 1 if rounded >= 10 else 2
    return f"{rounded:,.{decimals}f} {unit}"


def moment(timestamp: str, /) -> datetime.datetime:
    return datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def updated_text(timestamp: str | None, /) -> str:
    return "—" if timestamp is None else f"{moment(timestamp):%Y-%m-%d %H:%M}"


def staleness(timestamp: str | None, now: datetime.datetime, /) -> float | None:
    """How far a cache's last update is toward `STALE` when the table is drawn, from 0 to 1."""
    return None if timestamp is None else min(max((now - moment(timestamp)) / STALE, 0.0), 1.0)


def oklch(lightness: float, chroma: float, hue: float, /) -> str:
    """An OKLCH color as sRGB hex, clipping a channel that falls outside the gamut."""
    a, b = chroma * math.cos(math.radians(hue)), chroma * math.sin(math.radians(hue))
    long = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    medium = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    short = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    linear = (
        4.0767416621 * long - 3.3077115913 * medium + 0.2309699292 * short,
        -1.2684380046 * long + 2.6097574011 * medium - 0.3413193965 * short,
        -0.0041960863 * long - 0.7034186147 * medium + 1.7076147010 * short,
    )
    encoded = (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055 for v in linear)
    return "#" + "".join(f"{round(255 * min(max(v, 0.0), 1.0)):02x}" for v in encoded)


def cell(
    x: int,
    baseline: int,
    value: str,
    anchor: str = "start",
    numeric: bool = False,
    listed: bool = False,
    age: float | None = None,
) -> str:
    """One table cell; a missing value, a dash, is drawn muted, and one with an `age` from green to red."""
    flags = (("num", numeric), ("list", listed), ("none", value in ("—", ARCHIVE)), ("age", age is not None))
    classes = " ".join(name for name, on in flags if on)
    attribute = f' class="{classes}"' if classes else ""
    if age is not None:
        hue = FRESH_HUE + (STALE_HUE - FRESH_HUE) * age
        attribute += f' style="--age: {oklch(*AGE_LIGHT, hue)}; --age-dark: {oklch(*AGE_DARK, hue)}"'
    return f'<text x="{x}" y="{baseline}" text-anchor="{anchor}"{attribute}>{escape(value)}</text>'


def stack(x: int, baseline: int, names: list[str], /) -> list[str]:
    """A list of caches, one per line from the row's first baseline down."""
    return [cell(x, baseline + LINE * index, name, listed=True) for index, name in enumerate(names)]


def meter(baseline: int, fraction: float, kind: str, /) -> list[str]:
    """A bar of the Processed column with its percentage, on one line of a row."""
    middle = baseline - 4
    parts = [f'<rect class="track" x="{BAR_X}" y="{middle - 4}" width="{BAR_WIDTH}" height="8" rx="4"/>']
    if fraction > 0:
        width = max(BAR_WIDTH * fraction, 8)
        parts.append(f'<rect class="{kind}" x="{BAR_X}" y="{middle - 4}" width="{width:.1f}" height="8" rx="4"/>')
    return [*parts, cell(PERCENT_X, baseline, f"{100 * fraction:.1f}%", "end", numeric=True)]


def own_fraction(row: dict, /) -> float | None:
    return min(row["recorded"] / row["candidates"], 1.0) if row["candidates"] else None


def add_end_to_end(rows: list[dict], /) -> None:
    """Set each row's `end_to_end`: its own fraction times the end-to-end fraction of each of its inputs.

    An input that reports no fraction counts as whole, as nothing says otherwise. A row gets a value only
    when it reports a fraction of its own and something upstream is not whole.
    """
    by_name = {row["cache"]: row for row in rows}
    whole: dict[str, float] = {}

    def through(name: str, /) -> float:
        if name not in whole:
            row = by_name[name]
            whole[name] = own_fraction(row) or 1.0
            for source in row["sourcedata"]:
                if source in by_name:
                    whole[name] *= through(source)
        return whole[name]

    for row in rows:
        own = own_fraction(row)
        row["end_to_end"] = through(row["cache"]) if own is not None and through(row["cache"]) < own else None


def draw(rows: list[dict], now: datetime.datetime, /) -> str:
    heights = [
        ROW
        + LINE * (max(len(row["sourcedata"]), len(row["used_by"]), 2 if row.get("end_to_end") is not None else 1) - 1)
        for row in rows
    ]
    bottom = TOP + sum(heights)
    height = bottom + 40
    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" '
            'role="img" aria-labelledby="title desc">'
        ),
        '<title id="title">DANDI caches</title>',
        (
            f'<desc id="desc">Sources, size, last update and progress of {len(rows)} DANDI caches. '
            f"Updated {now:%Y-%m-%d %H:%M} UTC.</desc>"
        ),
        f"<style>{STYLE}</style>",
        f'<rect class="surface" width="{WIDTH}" height="{height}" rx="8"/>',
        f'<text class="updated" x="{PERCENT_X}" y="{height - 16}" text-anchor="end">'
        f"Table last updated: {now:%Y-%m-%d %H:%M} UTC</text>",
        f'<rect class="bar" x="{NAME_X}" y="{height - 25}" width="10" height="10" rx="2"/>',
        f'<text class="updated" x="{NAME_X + 16}" y="{height - 16}">Processed of its sourcedata</text>',
    ]
    # The end-to-end bar is drawn only where it is lower than the cache's own, so once everything upstream
    # is done there is none, and a legend entry for it would describe nothing on the table.
    if any(row.get("end_to_end") is not None for row in rows):
        lines += [
            f'<rect class="whole" x="{NAME_X + 200}" y="{height - 25}" width="10" height="10" rx="2"/>',
            f'<text class="updated" x="{NAME_X + 216}" y="{height - 16}">'
            "Processed end to end, through every cache upstream of it</text>",
        ]
    lines += [
        f'<text class="head" x="{NAME_X}" y="{TOP - 12}">Cache</text>',
        f'<text class="head" x="{SOURCE_X}" y="{TOP - 12}">Sourcedata</text>',
        f'<text class="head" x="{USED_BY_X}" y="{TOP - 12}">Used by</text>',
        f'<text class="head" x="{DATA_X}" y="{TOP - 12}" text-anchor="middle">data</text>',
        f'<text class="head" x="{FILES_X}" y="{TOP - 12}" text-anchor="middle">on disk</text>',
        f'<text class="head" x="{DIST_X}" y="{TOP - 12}" text-anchor="middle">dist</text>',
        f'<text class="head" x="{UPDATED_X}" y="{TOP - 12}" text-anchor="middle">Cache last updated (UTC)</text>',
        f'<text class="head" x="{PROCESSED_X}" y="{TOP - 12}" text-anchor="middle">Processed</text>',
        f'<line class="rule" x1="{NAME_X}" x2="{PERCENT_X}" y1="{TOP - 6}" y2="{TOP - 6}"/>',
    ]
    top = TOP
    for index, (row, row_height) in enumerate(zip(rows, heights)):
        baseline = top + 19
        top += row_height
        lines.append(cell(NAME_X, baseline, row["cache"]))
        lines += stack(SOURCE_X, baseline, row["sourcedata"] or [ARCHIVE])
        lines += stack(USED_BY_X, baseline, row["used_by"] or ["—"])
        lines.append(cell(DATA_X, baseline, human_size(row["derivatives_data"]), "middle", numeric=True))
        lines.append(cell(FILES_X, baseline, human_size(row["derivatives_files"]), "middle", numeric=True))
        lines.append(cell(DIST_X, baseline, human_size(row["dist_bytes"]), "middle", numeric=True))
        updated = updated_text(row["updated"])
        lines.append(cell(UPDATED_X, baseline, updated, "middle", numeric=True, age=staleness(row["updated"], now)))
        if (own := own_fraction(row)) is not None:
            lines += meter(baseline, own, "bar")
            if row.get("end_to_end") is not None:
                lines += meter(baseline + LINE, row["end_to_end"], "whole")
        else:
            lines.append(cell(PROCESSED_X, baseline, "—", "middle"))
        if index < len(rows) - 1:
            lines.append(f'<line class="rule" x1="{NAME_X}" x2="{PERCENT_X}" y1="{top - 1}" y2="{top - 1}"/>')
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def write_tsv(rows: list[dict], path: pathlib.Path, /) -> None:
    fields = [
        "cache",
        "sourcedata",
        "used_by",
        "derivatives_data",
        "derivatives_files",
        "dist_bytes",
        "updated",
        "recorded",
        "candidates",
        "end_to_end",
        "truncated",
    ]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            {
                **row,
                "sourcedata": ",".join(row["sourcedata"]),
                "used_by": ",".join(row["used_by"]),
                "end_to_end": None if row.get("end_to_end") is None else round(row["end_to_end"], 4),
            }
            for row in rows
        )


def layered(graph: dict[str, list[str]], /) -> dict[str, list[str]]:
    """The caches in the order the diagram reads, left to right and then top to bottom.

    A cache's column is the longest chain of inputs from the DANDI archive to it. Within a column,
    caches are ordered by where their inputs sit, so those built from the same sources sit together.
    """
    depth: dict[str, int] = {}

    def column(name: str, /) -> int:
        if name not in depth:
            depth[name] = 1 + max((column(source) for source in graph[name] if source in graph), default=0)
        return depth[name]

    position: dict[str, int] = {}
    for level in sorted({column(name) for name in graph}):
        here = [name for name in graph if depth[name] == level]

        def place(name: str, /) -> tuple[float, str]:
            placed = [position[source] for source in graph[name] if source in position]
            return (sum(placed) / len(placed) if placed else -1, name)

        for name in sorted(here, key=place):
            position[name] = len(position)
    return {name: graph[name] for name in sorted(graph, key=position.__getitem__)}


def mermaid(graph: dict[str, list[str]], /) -> str:
    """A flowchart of which cache feeds which, from the DANDI archive down."""
    nodes = [*graph, *sorted({source for sources in graph.values() for source in sources} - graph.keys())]
    lines = ["flowchart LR", f'    archive[("{ARCHIVE}")]']
    lines += [f'    {node.replace("-", "_")}["{node}"]' for node in nodes]
    for name, sources in graph.items():
        for source in sources or ["archive"]:
            lines.append(f'    {source.replace("-", "_")} --> {name.replace("-", "_")}')
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output", type=pathlib.Path, help="Where to write the SVG and the TSV.")
    parser.add_argument("--mermaid", action="store_true", help="Print the diagram of the inputs instead.")
    parser.add_argument("--cache", action="append", help="Only these caches (for trying it out); repeatable.")
    arguments = parser.parse_args()
    if not arguments.mermaid and arguments.output is None:
        parser.error("one of --output or --mermaid is required")

    graph = layered({name: inputs(name) or [] for name in arguments.cache} if arguments.cache else caches())
    if arguments.mermaid:
        print(mermaid(graph), end="")
        return 0
    rows = []
    for name, sources in graph.items():
        print(f"Reading {name}", file=sys.stderr)
        rows.append(describe(name, sources, sorted(user for user, used in graph.items() if name in used)))
    add_end_to_end(rows)
    now = datetime.datetime.now(datetime.timezone.utc)

    arguments.output.mkdir(parents=True, exist_ok=True)
    (arguments.output / "dashboard.svg").write_text(draw(rows, now))
    write_tsv(rows, arguments.output / "dashboard.tsv")
    for row in rows:
        if row["truncated"]:
            print(f"::warning::The tree of {row['cache']} was truncated, so its sizes are a lower bound.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
