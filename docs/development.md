# Development

## Columns

Sizes are in decimal units: 1 kB is 1000 bytes and 1 GB is 10⁹ bytes.

- **derivatives/ data**: the data under `derivatives/` on the cache's `derivatives` branch. A Zarr store counts the bytes of data it holds.
- **derivatives/ on disk**: the same files as they sit in a clone. A store's last chunk file is padded with newlines to the full chunk size, so a small cache takes a whole chunk per output; the padding compresses to almost nothing in git.
- **dist**: everything on the cache's `dist` branch, which is what it publishes, compressed.
- **Cache last updated**: when the `derivatives` branch last changed.
- **Processed**: how many of the cache's candidates are recorded, from the `Progress:` line the last run wrote to its log under `logs/`. A dash means the latest runs did not write one: the cache predates that line in `dandi-cache-utils`, or it selects its own batch.

## Branches

- `main` holds [`code/dashboard.py`](../code/dashboard.py), which reads every cache through the GitHub API, and the workflow that runs it every hour.
- `dashboard` holds the drawing and its TSV. Every run replaces it with a single commit, so it has no history of its own.
