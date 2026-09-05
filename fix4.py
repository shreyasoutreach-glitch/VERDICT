with open('backend/app/reconciler.py', 'r') as f:
    content = f.read()

old = "resolution_rate = (stats['resolved'] / stats['total']) * 100.0 if stats['total'] > 0 else 0.0"
new = "resolution_rate = (stats['resolved'] / stats['total']) * 100.0 if stats['total'] > 0 else 0.0\n    exact_match_rate = (stats['exact_match'] / stats['total']) * 100.0 if stats['total'] > 0 else 0.0"

content = content.replace(old, new)

with open('backend/app/reconciler.py', 'w') as f:
    f.write(content)
