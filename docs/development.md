# Development

## Columns

Sizes are in decimal units: 1 kB is 1000 bytes and 1 GB is 10⁹ bytes.

- **Sourcedata**: the caches the cache's `cache.toml` declares as `[[inputs]]`, one per line. *DANDI archive* means it declares none and reads the archive itself.
- **Used by**: the caches that declare it as an input.
- **Data**: the data under `derivatives/` on the cache's `derivatives` branch. A Zarr store counts the bytes of data it holds.
- **On disk**: the same files as they sit in a clone. A store's last chunk file is padded with newlines to the full chunk size, so a small cache takes a whole chunk per output; the padding compresses to almost nothing in git.
- **dist**: everything on the cache's `dist` branch, which is what it publishes, compressed.
- **Cache last updated**: when the `derivatives` branch last changed.
- **Processed**: how many of the cache's candidates are recorded, from the `Progress:` line the last run wrote to its log under `logs/`. A dash means the latest runs did not write one: the cache predates that line in `dandi-cache-utils`, or it selects its own batch.

## Row order

The rows follow the README's diagram, left to right and then top to bottom. Each run writes the diagram, has Mermaid lay it out with [mermaid-cli](https://github.com/mermaid-js/mermaid-cli), and orders the rows by where each cache landed. Should that step fail, the rows fall back to an approximation: by the longest chain of inputs from the archive, then by where a cache's inputs sit.

## Branches

- `main` holds [`code/dashboard.py`](../code/dashboard.py), which reads every cache through the GitHub API, and the workflow that runs it every hour.
- `dashboard` holds the drawing and its TSV. Every run replaces it with a single commit, so it has no history of its own.

## The diagram

The README's diagram of how the caches feed each other is written by hand from `python3 code/dashboard.py --mermaid`, since a README can only show a Mermaid diagram written into it. Run it again and paste the output when a cache is added or changes its inputs.
