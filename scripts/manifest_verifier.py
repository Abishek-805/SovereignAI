import hashlib
import json
import logging
from pathlib import Path
import sys

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def verify_manifest(manifest_path: Path):
    if not manifest_path.exists():
        logger.error(f"Manifest not found: {manifest_path}")
        return False
        
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as e:
        logger.error(f"Failed to parse manifest: {e}")
        return False
        
    root_dir = manifest_path.parent.resolve()
    files = manifest.get('files')
    if not isinstance(files,list) or not files:
        logger.error('Manifest must list at least one file')
        return False
    all_passed = True
    seen=set()
    
    for file_info in files:
        if not isinstance(file_info,dict):
            all_passed=False
            continue
        rel_path = file_info.get('path')
        expected_hash = file_info.get('sha256')
        
        if not isinstance(rel_path,str) or not rel_path or not isinstance(expected_hash,str) or len(expected_hash)!=64 or any(ch not in '0123456789abcdef' for ch in expected_hash.lower()):
            logger.error('Invalid manifest entry')
            all_passed=False
            continue
        full_path = (root_dir / rel_path).resolve()
        if rel_path in seen or not full_path.is_relative_to(root_dir) or full_path==root_dir:
            logger.error(f'Unsafe or duplicate manifest path: {rel_path}')
            all_passed=False
            continue
        seen.add(rel_path)
        if not full_path.is_file():
            logger.error(f"MISSING: {rel_path}")
            all_passed = False
            continue
        if 'size' in file_info and full_path.stat().st_size!=file_info['size']:
            logger.error(f'SIZE MISMATCH: {rel_path}')
            all_passed=False
            continue
            
        hasher = hashlib.sha256()
        try:
            with open(full_path, 'rb') as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            
            actual_hash = hasher.hexdigest()
            if actual_hash != expected_hash:
                logger.error(f"HASH MISMATCH: {rel_path} (Expected {expected_hash}, got {actual_hash})")
                all_passed = False
            else:
                logger.info(f"OK: {rel_path}")
        except Exception as e:
            logger.error(f"ERROR reading {rel_path}: {e}")
            all_passed = False
            
    return all_passed

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        target = Path(__file__).resolve().parents[1] / 'setup-staging' / 'manifest.json'
        
    success = verify_manifest(target)
    sys.exit(0 if success else 1)
