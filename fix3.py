import re

with open('backend/app/reconciler.py', 'r') as f:
    content = f.read()

old_sql_call = r'conn\.execute\("""\s*INSERT INTO reconciliation_batches.*?\) \+ "Z".*?\)\)'

new_sql_call = '''conn.execute("""
            INSERT INTO reconciliation_batches 
            (batch_id, created_at, total_records, resolved_count, exact_match_count, normalized_match_count, ambiguous_count, mismatch_count, missing_count, duplicate_count, unresolved_count, resolution_rate, exact_match_rate, processing_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_id, datetime.utcnow().isoformat() + "Z", stats['total'], stats['resolved'], stats['exact_match'], stats['normalized_match'], stats['ambiguous'], stats['mismatch'], stats['missing'], stats['duplicate'], stats['unresolved'], resolution_rate, exact_match_rate, processing_time_ms))'''

content = re.sub(old_sql_call, new_sql_call, content, flags=re.DOTALL)

with open('backend/app/reconciler.py', 'w') as f:
    f.write(content)
