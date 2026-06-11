import hashlib
from pathlib import Path


def compute_file_sha256(file_path: str | None) -> str | None:
    """
    SHA-256 (hex minúsculo) do arquivo em disco, lido em blocos de 1 MiB.
    Retorna None se o caminho for vazio ou o arquivo não existir.

    É a base da "verificabilidade prática pelo arquivo": o hash registrado
    no upload só tem valor probatório se o sistema reconferir, nos momentos
    críticos (assinatura, validação pública), que o arquivo armazenado
    continua produzindo exatamente esse hash.
    """
    if not file_path:
        return None
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return None

    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
