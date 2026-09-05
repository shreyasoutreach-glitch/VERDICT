import re

with open('backend/app/reconciler.py', 'r') as f:
    content = f.read()

content = re.sub(r'\"matched\": 0,', '\"resolved\": 0, \"exact_match\": 0, \"normalized_match\": 0,', content)
content = content.replace("stats['matched'] += 1", "stats['resolved'] += 1")
content = content.replace('stats[\'resolved\'] += 1\n            elif len(amount_matches) > 1:', 'stats[\'resolved\'] += 1\n                stats[\'normalized_match\'] += 1\n            elif len(amount_matches) > 1:')
content = content.replace('stats[\'resolved\'] += 1\n                else:', 'stats[\'resolved\'] += 1\n                    stats[\'normalized_match\'] += 1\n                else:')
content = content.replace('stats[\'resolved\'] += 1\n            else:', 'stats[\'resolved\'] += 1\n                stats[\'exact_match\'] += 1\n            else:')

content = content.replace('resolution_rate = (stats[\'resolved\'] / stats[\'total\']) * 100.0 if stats[\'total\'] > 0 else 0.0', 'resolution_rate = (stats[\'resolved\'] / stats[\'total\']) * 100.0 if stats[\'total\'] > 0 else 0.0\n    exact_match_rate = (stats[\'exact_match\'] / stats[\'total\']) * 100.0 if stats[\'total\'] > 0 else 0.0')

sql_old = '''        conn.execute("""
            INSERT INTO reconciliation_batches 
            (batch_id, created_at, total_records, matched_count, ambiguous_count, mismatch_count, missing_count, duplicate_count, unresolved_count, resolution_rate, processing_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_id, datetime.utcnow().isoformat() + "Z", stats['total'], stats['resolved'], stats['ambiguous'], stats['mismatch'], stats['missing'], stats['duplicate'], stats['unresolved'], resolution_rate, processing_time_ms))'''

sql_new = '''        conn.execute("""
            INSERT INTO reconciliation_batches 
            (batch_id, created_at, total_records, resolved_count, exact_match_count, normalized_match_count, ambiguous_count, mismatch_count, missing_count, duplicate_count, unresolved_count, resolution_rate, exact_match_rate, processing_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_id, datetime.utcnow().isoformat() + "Z", stats['total'], stats['resolved'], stats['exact_match'], stats['normalized_match'], stats['ambiguous'], stats['mismatch'], stats['missing'], stats['duplicate'], stats['unresolved'], resolution_rate, exact_match_rate, processing_time_ms))'''

content = content.replace(sql_old, sql_new)

with open('backend/app/reconciler.py', 'w') as f:
    f.write(content)
