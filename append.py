code = """
@app.post('/api/reconcile')
def run_reconciliation():
    from .reconciler import run_reconciliation_batch
    batch_id = run_reconciliation_batch()
    return {'batch_id': batch_id}

@app.get('/api/reconciliation/latest')
def get_latest_batch():
    with db.get_conn() as conn:
        row = conn.execute('SELECT * FROM reconciliation_batches ORDER BY created_at DESC LIMIT 1').fetchone()
    if not row:
        return None
    return db.row_to_dict(row)

@app.get('/api/reconciliation/records')
def get_reconciliation_records(batch_id: str = None):
    with db.get_conn() as conn:
        if not batch_id:
            batch = conn.execute('SELECT batch_id FROM reconciliation_batches ORDER BY created_at DESC LIMIT 1').fetchone()
            if not batch:
                return []
            batch_id = batch[0]
        rows = conn.execute('SELECT * FROM reconciliation_records WHERE batch_id = ?', (batch_id,)).fetchall()
    return [db.row_to_dict(r) for r in rows]

@app.get('/api/reconciliation/exceptions')
def get_reconciliation_exceptions(batch_id: str = None):
    with db.get_conn() as conn:
        if not batch_id:
            batch = conn.execute('SELECT batch_id FROM reconciliation_batches ORDER BY created_at DESC LIMIT 1').fetchone()
            if not batch:
                return []
            batch_id = batch[0]
        rows = conn.execute('SELECT * FROM reconciliation_exceptions WHERE batch_id = ?', (batch_id,)).fetchall()
    return [db.row_to_dict(r) for r in rows]

@app.post('/api/chaos/reconciliation/{mutation_type}')
def inject_reconciliation_chaos(mutation_type: str):
    with db.get_conn() as conn:
        row = conn.execute("SELECT true_target_record_id, source_record_id FROM reconciliation_ground_truth WHERE expected_status = 'MATCHED' LIMIT 1").fetchone()
        if not row:
            raise HTTPException(status_code=400, detail='No matching records available to mutate')
        t_id = row[0]
        
        if mutation_type == 'amount_mismatch':
            conn.execute('UPDATE tally_ledger SET amount = amount + 1500 WHERE entry_id = ?', (t_id,))
            conn.commit()
        elif mutation_type == 'delete':
            conn.execute('DELETE FROM tally_ledger WHERE entry_id = ?', (t_id,))
            conn.commit()
        elif mutation_type == 'duplicate':
            orig = db.row_to_dict(conn.execute('SELECT * FROM tally_ledger WHERE entry_id = ?', (t_id,)).fetchone())
            conn.execute('INSERT INTO tally_ledger (entry_id, order_id, entry_type, amount, entry_date) VALUES (?, ?, ?, ?, ?)',
                         (orig['entry_id'] + '-DUP', orig['order_id'], orig['entry_type'], orig['amount'], orig['entry_date']))
            conn.commit()
        elif mutation_type == 'date_mismatch':
            conn.execute("UPDATE tally_ledger SET entry_date = datetime(entry_date, '+10 days') WHERE entry_id = ?", (t_id,))
            conn.commit()
            
        return {'mutated': True, 'target': t_id}
"""

with open('backend/app/main.py', 'a') as f:
    f.write(code)
