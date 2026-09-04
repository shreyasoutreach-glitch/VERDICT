"""
Claim extraction. In this prototype the upstream agent already writes a
structured sidecar (see evidence_generator.py), so extraction is a read,
not an NLP problem. Kept as its own pipeline stage -- rather than inlined
into the DB layer -- because a production version would replace only
this module (parsing free-text evidence into the same claim schema) and
nothing downstream would need to change.
"""
from __future__ import annotations

from .. import db


def extract_claims(dispute_id: str) -> list[dict]:
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM claims WHERE dispute_id = ?", (dispute_id,)).fetchall()
    return [db.row_to_dict(r) for r in rows]
