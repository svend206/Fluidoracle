import hashlib


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def source_id(url: str, vertical: str, phase: int) -> str:
    key = f"{url}|{vertical}|{phase}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
