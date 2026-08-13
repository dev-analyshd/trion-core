#!/usr/bin/env python3
"""
Phase 2.1 helper: apply @require_entity_id() decorator to all Flask routes
that accept <entity_id> path parameters in api/app.py.

Skips routes that already have the decorator. Idempotent.
"""
import re
from pathlib import Path

APP_PY = Path('/home/z/my-project/repos/trion-core/api/app.py')

# Match: @app.route("/...<entity_id>...")\n[optional existing decorators]\ndef funcname(entity_id...):
# We insert @require_entity_id() between the @app.route and the def, but only
# if it's not already present.
ROUTE_RE = re.compile(
    r'^(@app\.route\("/api/v1/[^"]*<entity_id>[^"]*"(?:, methods=\[[^\]]*\])?\))\n'
    r'((?:(?:@[a-zA-Z_][a-zA-Z0-9_().]*\n)*))'
    r'(def [a-zA-Z_][a-zA-Z0-9_]*\(entity_id[^)]*\):)',
    re.MULTILINE,
)

src = APP_PY.read_text()
matches = list(ROUTE_RE.finditer(src))
print(f"Found {len(matches)} routes with <entity_id>")

modified = 0
skipped = 0
for m in matches:
    route_line = m.group(1)
    existing_decorators = m.group(2)
    def_line = m.group(3)
    if 'require_entity_id' in existing_decorators:
        skipped += 1
        continue
    new_block = f"{route_line}\n{existing_decorators}@require_entity_id()\n{def_line}"
    src = src[:m.start()] + new_block + src[m.end():]
    modified += 1

APP_PY.write_text(src)
print(f"Applied @require_entity_id() to {modified} routes (skipped {skipped} already-decorated)")
