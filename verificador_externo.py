#!/usr/bin/env python3
"""
Verificador externo e independente de assinaturas LockIn.

Este script NÃO usa nenhum código do LockIn. Ele recebe apenas os dados
PÚBLICOS expostos pelo endpoint de validação (GET /public/signatures/{codigo})
e reproduz, do zero, toda a verificação criptográfica descrita no Capítulo 5:

  1. Recomputa o fingerprint da assinatura (SHA-256 dos bytes da assinatura).
  2. Recomputa o fingerprint da chave pública (SHA-256 do DER SubjectPublicKeyInfo).
  3. Recomputa H_evento a partir da serialização canônica (prefixada por comprimento).
  4. Reproduz o hash-to-prime com o contador publicado e confere x_i.
  5. (opcional) Confirma que x_i é primo (Miller-Rabin).
  6. Verifica a assinatura RSA-PSS contra o HASH PUBLICADO
     (mensagem = hash SHA-256 em hexadecimal minúsculo, 64 caracteres ASCII;
      SHA-256 + MGF1-SHA-256 + salt de 32 bytes).
  7. Verifica o pertencimento no acumulador: pi_i^x_i ≡ A_i (mod N).
  8. (opcional) Re-deriva a base g = h² mod N e confere com a publicada.
  9. (opcional) Se receber o PDF original (download autorizado), recomputa o
     SHA-256 do arquivo e compara com o hash publicado.

Dependência externa: apenas a biblioteca `cryptography` (pip install cryptography).
Tudo o mais é biblioteca padrão do Python.

Uso:
  # a partir do endpoint público
  python verificador_externo.py --url https://HOST/public/signatures/CODIGO
  python verificador_externo.py --base https://HOST --code CODIGO

  # a partir de um JSON já salvo
  python verificador_externo.py --json resposta.json

  # conferindo também os bytes do PDF original (baixado de forma autorizada)
  python verificador_externo.py --json resposta.json --pdf documento-original.pdf

Código de saída: 0 se todas as verificações obrigatórias passarem, 1 caso contrário.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import sys
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature


# --------------------------------------------------------------------------- #
# Constantes de domínio (públicas, idênticas às do esquema; também vêm no JSON) #
# --------------------------------------------------------------------------- #
H2P_DOMAIN = "H2P-V1"                 # separação de domínio do hash-to-prime
BASE_DOMAIN = "ACCUMULATOR-BASE-V1"   # separação de domínio da base g

# Ordem e NOMES canônicos dos campos do evento. ATENÇÃO: o nome canônico é
# "versao" (no JSON do endpoint a chave aparece como "versao_formato").
CANONICAL_FIELDS = [
    ("dominio", "dominio"),
    ("versao", "versao_formato"),
    ("hash_documento", "hash_documento"),
    ("hash_assinatura", "hash_assinatura"),
    ("hash_chave_publica", "hash_chave_publica"),
    ("codigo_publico", "codigo_publico"),
    ("timestamp_iso8601", "timestamp_iso8601"),
]


# --------------------------------------------------------------------------- #
# Utilitários de impressão                                                     #
# --------------------------------------------------------------------------- #
class Report:
    def __init__(self) -> None:
        self.ok = True

    def check(self, label: str, passed: bool, detail: str = "") -> bool:
        mark = "PASS" if passed else "FALHA"
        line = f"  [{mark}] {label}"
        if detail:
            line += f"\n         {detail}"
        print(line)
        if not passed:
            self.ok = False
        return passed

    def info(self, label: str, detail: str = "") -> None:
        line = f"  [ -- ] {label}"
        if detail:
            line += f"\n         {detail}"
        print(line)


# --------------------------------------------------------------------------- #
# Primitivas reproduzidas (independentes do LockIn)                            #
# --------------------------------------------------------------------------- #
def canonical_event_hash(fields: list[tuple[str, str]]) -> str:
    """SHA-256 da serialização canônica prefixada por comprimento."""
    payload = bytearray()
    for name, value in fields:
        nb = name.encode("utf-8")
        vb = value.encode("utf-8")
        payload += len(nb).to_bytes(4, "big") + nb
        payload += len(vb).to_bytes(4, "big") + vb
    return hashlib.sha256(bytes(payload)).hexdigest()


def hash_to_prime_candidate(event_hash_hex: str, nonce: int) -> int:
    """Reproduz o candidato do hash-to-prime no contador publicado."""
    raw = f"{H2P_DOMAIN}:{event_hash_hex}:{nonce}".encode("ascii")
    candidate = int(hashlib.sha256(raw).hexdigest(), 16)
    candidate |= 1  # tornado ímpar
    return candidate


def is_probable_prime(n: int, rounds: int = 40) -> bool:
    """Miller-Rabin determinístico para bases pequenas + algumas aleatórias fixas."""
    if n < 2:
        return False
    small_primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    for p in small_primes:
        if n % p == 0:
            return n == p
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    bases = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    for a in bases[:rounds]:
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def derive_base(modulus_n: int, start_counter: int = 0) -> tuple[int, int]:
    """Re-deriva a base g = h² mod N de forma determinística."""
    counter = start_counter
    n_bytes = (modulus_n.bit_length() + 7) // 8
    modulus_bytes = modulus_n.to_bytes(n_bytes, "big")
    while True:
        digest = hashlib.sha256(
            f"{BASE_DOMAIN}:".encode("ascii")
            + modulus_bytes
            + f":{counter}".encode("ascii")
        ).digest()
        h = int.from_bytes(digest, "big") % modulus_n
        if h > 1 and math.gcd(h, modulus_n) == 1:
            g = pow(h, 2, modulus_n)
            if g not in (0, 1):
                return g, counter
        counter += 1


# --------------------------------------------------------------------------- #
# Carregamento dos dados públicos                                              #
# --------------------------------------------------------------------------- #
def load_payload(args: argparse.Namespace) -> dict:
    if args.json:
        with open(args.json, "r", encoding="utf-8") as fh:
            return json.load(fh)
    url = args.url
    if not url and args.base and args.code:
        url = f"{args.base.rstrip('/')}/public/signatures/{args.code}"
    if not url:
        raise SystemExit("Forneça --json, --url, ou --base e --code.")
    with urllib.request.urlopen(url) as resp:  # noqa: S310 (URL controlada pelo usuário)
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------- #
# Verificação                                                                  #
# --------------------------------------------------------------------------- #
def verificar(payload: dict, pdf_path: str | None) -> bool:
    ev = payload["evento_de_assinatura"]
    rsa = payload["prova_tecnica"]["assinatura_rsa"]
    acc = payload["prova_tecnica"]["pertencimento_ao_acumulador"]
    doc = payload["documento"]

    r = Report()
    print(f"\nVerificando código: {payload.get('codigo_de_validacao')}")
    print(f"Status declarado pela plataforma: {payload.get('status')}\n")

    # Dados públicos
    signature_b64 = rsa["signature_base64"]
    public_key_pem = rsa["public_key_pem"]
    sig_bytes = base64.b64decode(signature_b64, validate=True)
    public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))

    document_hash_hex = ev["hash_documento"]
    N = int(acc["modulo_n_hex"], 16)
    g = int(acc["gerador_hex"], 16)
    g_counter = int(acc["gerador_contador"])
    x_i = int(acc["x_hex"], 16)
    x_nonce = int(acc["x_nonce"])
    A_i = int(acc["acumulador_hex"], 16)
    pi_i = int(acc["witness_hex"], 16)

    print("== 1. Fingerprints recomputados a partir dos dados públicos ==")
    calc_sig_fp = hashlib.sha256(sig_bytes).hexdigest()
    r.check(
        "hash_assinatura = SHA-256(bytes da assinatura)",
        calc_sig_fp == ev["hash_assinatura"],
        f"calculado={calc_sig_fp[:16]}… publicado={ev['hash_assinatura'][:16]}…",
    )
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    calc_key_fp = hashlib.sha256(der).hexdigest()
    r.check(
        "hash_chave_publica = SHA-256(DER SubjectPublicKeyInfo)",
        calc_key_fp == ev["hash_chave_publica"],
        f"calculado={calc_key_fp[:16]}… publicado={ev['hash_chave_publica'][:16]}…",
    )

    print("\n== 2. H_evento reconstruído da serialização canônica ==")
    fields = [(canonical, ev[json_key]) for canonical, json_key in CANONICAL_FIELDS]
    calc_event_hash = canonical_event_hash(fields)
    r.check(
        "H_evento reproduzível",
        calc_event_hash == ev["hash_evento"],
        f"calculado={calc_event_hash[:16]}… publicado={ev['hash_evento'][:16]}…",
    )

    print("\n== 3. hash-to-prime reproduzido (representante x_i) ==")
    calc_x = hash_to_prime_candidate(calc_event_hash, x_nonce)
    r.check(
        f"x_i derivado de H_evento e do contador c_i={x_nonce}",
        calc_x == x_i,
        f"calculado={hex(calc_x)[:18]}… publicado={hex(x_i)[:18]}…",
    )
    r.check("x_i é primo (Miller-Rabin)", is_probable_prime(x_i))

    print("\n== 4. Assinatura RSA-PSS contra o HASH PUBLICADO ==")
    # Mensagem assinada = hash SHA-256 do documento em hex minúsculo, ASCII.
    message = document_hash_hex.encode("ascii")
    try:
        public_key.verify(
            sig_bytes,
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
            hashes.SHA256(),
        )
        rsa_ok = True
    except InvalidSignature:
        rsa_ok = False
    r.check(
        "RSA-PSS(SHA-256, MGF1-SHA-256, salt=32) sobre o hash hex (ASCII)",
        rsa_ok,
    )

    print("\n== 5. Pertencimento no acumulador ==")
    membership_ok = pow(pi_i, x_i, N) == A_i
    r.check("pi_i^x_i ≡ A_i (mod N)", membership_ok)

    print("\n== 6. Re-derivação da base g (independente) ==")
    calc_g, calc_counter = derive_base(N, 0)
    r.check(
        "g = h² mod N re-derivada confere com a publicada",
        calc_g == g and calc_counter == g_counter,
        f"contador calculado={calc_counter} publicado={g_counter}",
    )

    print("\n== 7. Conferência dos bytes do PDF (opcional, requer download autorizado) ==")
    if pdf_path:
        with open(pdf_path, "rb") as fh:
            pdf_hash = hashlib.sha256(fh.read()).hexdigest()
        r.check(
            "SHA-256(PDF original) == hash publicado",
            pdf_hash == document_hash_hex,
            f"arquivo={pdf_hash[:16]}… publicado={document_hash_hex[:16]}…",
        )
    else:
        r.info(
            "PDF não fornecido",
            "Passe --pdf para conferir os bytes (download exige autenticação: "
            "empresa proprietária ou signatário).",
        )

    print()
    if r.ok:
        print("RESULTADO: TODAS as verificações criptográficas independentes PASSARAM.")
        print("A consistência foi estabelecida SEM depender da plataforma LockIn.")
    else:
        print("RESULTADO: ALGUMA verificação FALHOU. Os dados são inconsistentes.")
    return r.ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verificador externo e independente de assinaturas LockIn."
    )
    parser.add_argument("--json", help="Arquivo JSON com a resposta do endpoint público.")
    parser.add_argument("--url", help="URL completa do endpoint público de validação.")
    parser.add_argument("--base", help="Base da API (ex.: https://host). Use com --code.")
    parser.add_argument("--code", help="Código de validação. Use com --base.")
    parser.add_argument("--pdf", help="Caminho do PDF original para conferir os bytes.")
    args = parser.parse_args()

    payload = load_payload(args)
    ok = verificar(payload, args.pdf)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
