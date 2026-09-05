import sqlite3
conn = sqlite3.connect('backend/veridict.db')
print(conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='reconciliation_batches'").fetchone()[0])
