"""Stable signatures for observed validation errors; never generates feedback."""
import hashlib
import re

def failure_fingerprint(feedback):
    lines=str(feedback).strip().splitlines()
    exceptions=[line.strip() for line in lines if re.fullmatch(r'[A-Za-z_][\w.]*(?:Error|Exception)(?::.*)?',line.strip())]
    signature=exceptions[-1] if exceptions else str(feedback).strip()[-3000:]
    # Diagnostic digests identify an observation, not the underlying failure.
    signature=re.sub(r'\b[a-fA-F0-9]{64}\b','<digest>',signature)
    return hashlib.sha256(signature.encode('utf-8')).hexdigest()
