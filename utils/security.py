import hashlib, secrets
from hmac import compare_digest

def generate_salt() -> str:
    return secrets.token_hex(16)

def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode()).hexdigest()

def verify_password(plain: str, stored_hash: str, salt: str) -> bool:
    return compare_digest(hash_password(plain, salt), stored_hash)
