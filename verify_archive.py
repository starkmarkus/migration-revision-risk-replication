"""Verify the complete extracted supplement tree before rerunning the analysis."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'MANIFEST.json').read_text(encoding='utf-8'))
errors=[]
for name,expected in manifest['sha256'].items():
    file=(ROOT/name).resolve()
    if not file.is_relative_to(ROOT) or not file.is_file():
        errors.append('Missing or invalid path: '+name)
    elif hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
        errors.append('Hash mismatch: '+name)
if errors:
    print('\n'.join(errors))
    raise SystemExit(1)
print(f"Verified {len(manifest['sha256'])} files for {manifest['version']}.")
print('Rerunning the analysis can change derived-file hashes and execution logs.')
