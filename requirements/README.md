# Locked Dependencies

This directory contains pip-compile managed requirements with locked transitive dependencies.

## Structure

- `base.in` — Base production dependencies (loosely specified)
- `base.txt` — Locked production dependencies (all transitive deps pinned)
- `dev.in` — Development dependencies (loosely specified, includes base)
- `dev.txt` — Locked development dependencies (all transitive deps pinned)

## Usage

**Local development:**
```bash
pip install -r ../requirements-dev.txt
```

**Production:**
```bash
pip install -r ../requirements.txt
```

## Updating locked versions

When you need to update dependencies:

```bash
# Install pip-tools
pip install pip-tools

# Update production dependencies
pip-compile requirements/base.in -o requirements/base.txt

# Update dev dependencies (regenerates base.txt deps too)
pip-compile requirements/dev.in -o requirements/dev.txt
```

This ensures reproducible installs across all machines and environments.
