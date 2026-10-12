# dandi-cache-dashboard

A quick reference for the current state of every [DANDI cache](https://github.com/dandi-cache).

![DANDI caches](https://raw.githubusercontent.com/dandi-cache/dandi-cache-dashboard/dashboard/dashboard.svg)

The same numbers are in [`dashboard.csv`](https://github.com/dandi-cache/dandi-cache-dashboard/blob/dashboard/dashboard.csv), in bytes.

## Columns

- **derivatives/ data**: the data under `derivatives/` on the cache's `derivatives` branch. A Zarr store counts the bytes of data it holds.
- **derivatives/ on disk**: the same files as they sit in a clone. A store's last chunk file is padded with newlines to the full chunk size, so a small cache takes a whole chunk per output; the padding compresses to almost nothing in git.
- **dist**: everything on the cache's `dist` branch, which is what it publishes, compressed.
- **Last updated**: when the `derivatives` branch last changed.
- **Processed**: how many of the cache's candidates are recorded, from the `Progress:` line the last run wrote to its log under `logs/`. A dash means the latest runs did not write one: the cache predates that line in `dandi-cache-utils`, or it selects its own batch.
