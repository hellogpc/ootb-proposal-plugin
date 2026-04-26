#!/usr/bin/env python3
"""DEPRECATED — v1 (direct Supabase client). Kept only as reference.

This skill has moved to MCP-driven ingest. Use instead:

    python prep.py <file.pdf> -o /tmp/payload.json

Then Claude runs the `sql_upsert` from the JSON via `mcp__supabase__execute_sql`.
See SKILL.md (Path B) and references/mcp_playbook.md for details.
"""
import sys
print(__doc__, file=sys.stderr)
sys.exit(1)
