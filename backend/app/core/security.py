"""Senhas (SEC-01) e tokens opacos (SEC-03, SEC-04)."""

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Parâmetros padrão do argon2-cffi (Argon2id, 64 MiB, t=3, p=4) — acima do mínimo OWASP.
_hasher = PasswordHasher()
# Hash fictício para gastar o mesmo tempo quando o e-mail não existe (antienumeração).
_DUMMY_HASH = _hasher.hash("senha-ficticia-para-tempo-constante")

MIN_PASSWORD = 12
MAX_PASSWORD = 128

# Lista local curta de senhas comuns com 12+ caracteres. Nenhuma senha é enviada a terceiros.
# Ampliar carregando uma lista maior de arquivo é uma evolução registrada (doc 09 SEC-01).
COMMON_PASSWORDS = frozenset(
    {
        "123456789012", "1234567890123", "12345678901234", "123123123123",
        "111111111111", "000000000000", "qwertyuiopas", "qwertyuiop123",
        "password1234", "password12345", "passwordpassword", "senha1234567",
        "senhasenha12", "senhasenhasenha", "abcdefghijkl", "abc123abc123",
        "iloveyou1234", "admin1234567", "administrador", "boardhub1234",
        "aaaaaaaaaaaa", "1q2w3e4r5t6y", "1qaz2wsx3edc", "zaq12wsxcde3",
    }
)


def password_problem(password: str) -> str | None:
    """Retorna a razão de rejeição ou None se a senha é aceitável."""
    if len(password) < MIN_PASSWORD:
        return f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres."
    if len(password) > MAX_PASSWORD:
        return f"A senha pode ter no máximo {MAX_PASSWORD} caracteres."
    if password.lower() in COMMON_PASSWORDS or len(set(password)) < 4:
        return "Essa senha é muito comum ou repetitiva. Escolha outra."
    return None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_token() -> str:
    """Token opaco de 256 bits, seguro para URL."""
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> bytes:
    """Somente o SHA-256 do token é armazenado."""
    return hashlib.sha256(token.encode()).digest()


def tokens_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
