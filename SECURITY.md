# Security Notes

Do not commit local secrets or machine-specific runtime files.

Keep these out of Git:

- `config/settings.yml`
- SearXNG `secret_key`
- GitHub tokens
- OpenClaw private config files
- `.venv/`
- downloaded SearXNG source zips
- SearXNG logs and PID files

This repository contains deployment scripts and templates only. SearXNG itself is not vendored here; it is downloaded from the upstream SearXNG project during install.
