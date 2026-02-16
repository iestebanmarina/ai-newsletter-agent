# Scripts

Utility and administrative scripts for the newsletter system.

## Available Scripts

### `fix_email_via_api.py`
Updates a subscriber's email address via the dashboard API.

**Usage:**
```bash
uv run python scripts/fix_email_via_api.py
```

Edit the `OLD_EMAIL` and `NEW_EMAIL` variables in the script, or set `DASHBOARD_PASSWORD` environment variable.

---

## Guidelines

### What goes in `scripts/`:
- ✅ Administrative utilities (database fixes, migrations, bulk operations)
- ✅ Development helpers (seed data, test data generators)
- ✅ Operational tools (monitoring, diagnostics, reports)
- ✅ Scripts that need to be versioned and maintained

### What does NOT go in `scripts/`:
- ❌ Temporary debugging scripts (use local files, add pattern to `.gitignore`)
- ❌ One-off exploratory code (create outside repo or use `temp/` folder)
- ❌ Personal testing scripts (keep locally, don't commit)

**Temporary scripts pattern:** If you create debugging scripts like `check_*.py` or `*_test.py`, they're automatically ignored by git.
