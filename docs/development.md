# Development

## Branches

- `main` holds [`code/dashboard.py`](../code/dashboard.py), which reads every cache through the GitHub API, and the workflow that runs it every hour.
- `dashboard` holds the drawing and its CSV. Every run replaces it with a single commit, so it has no history of its own.

A cache is any repository of the organization with a `cache.toml` at its root, other than the template, so a new cache appears on its own.
