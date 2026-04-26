#!/usr/bin/env python3
"""DEPRECATED — v1 (direct Supabase client). Kept only as reference.

Search has moved to Supabase MCP + local embed helper. Use instead:

    python embed_query.py "질의 문장"        # prints vector literal

Then Claude runs `mcp__supabase__execute_sql` on the `match_proposals` RPC
with that vector. See SKILL.md (Path C) and references/mcp_playbook.md.
"""
import sys
print(__doc__, file=sys.stderr)
sys.exit(1)
