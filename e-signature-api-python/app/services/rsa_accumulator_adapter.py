import hashlib
import math
import secrets
from dataclasses import dataclass
from typing import Protocol


MIN_GENERATOR_VALUE = 2

# Separação de domínio (e versão) das funções determinísticas do acumulador.
# As tags entram nas pré-imagens dos hashes para que valores derivados aqui não
# colidam com hashes produzidos em outros contextos e para versionar a
# derivação, permitindo a reprodução externa por um verificador independente.
H2P_DOMAIN = "H2P-V1"                              # hash-to-prime
ACCUMULATOR_BASE_DOMAIN = "ACCUMULATOR-BASE-V1"    # derivação da base g

# ---------------------------------------------------------------------------
# Módulo RSA de ordem desconhecida (Unknown-Order RSA Modulus)
#
# Fonte: RSA Factoring Challenge — RSA-2048
#   https://www.rsa.com/rsalabs/node.asp?id=2093
#
# Este número de 617 dígitos (2048 bits) foi gerado pela RSA Security para o
# "RSA Factoring Challenge". Sua fatoração permanece desconhecida publicamente.
#
# Por que usar este número?
#   O acumulador RSA requer um módulo N = p·q cuja fatoração seja desconhecida
#   de TODOS os participantes, inclusive o servidor (premissa de ordem desconhecida,
#   *unknown-order assumption*). Se o servidor gerar N com rsa.generate_private_key(),
#   ele conhece p e q e pode calcular φ(N) = (p-1)(q-1), o que permite forjar
#   qualquer testemunha via:  w_forjada = pow(S, e⁻¹ mod φ(N), N).
#
# Usando RSA-2048:
#   - Ninguém conhece φ(N), logo testemunhas não podem ser forjadas.
#   - O número é público: qualquer verificador pode reproduzir o acumulador.
#   - Dispensa cerimônia de trusted setup ou MPC multi-party.
#   - Academicamente referenciado em Boneh et al. (2019), Wesolowski (2019).
# ---------------------------------------------------------------------------
RSA_2048_CHALLENGE_N = int(
    "2519590847565789349402718324004839857142928212620403202777713783604366202070759"
    "5556264018525880784406918290641249515082189298559149176184502808489120072844992"
    "6873928072877767359714183472702618963750149718246911650776133798590957000973304"
    "5974880842840179742910064245869181719511874612151517265463228221686998754918242"
    "2433637259085141865462043576798423387184774447920739934236584823824281198163815"
    "0106748104516603773060562016196762561338441436038339044149526344321901146575444"
    "5417842402092461651572335077870774981712577246796292638635637328991215483143816"
    "7899885040445364023527381951378636564391212010397122822120720357"
)


@dataclass(frozen=True)
class HashPrimeResult:
    prime: int
    nonce: int


@dataclass(frozen=True)
class AccumulatorComputation:
    x_value: int
    x_nonce: int
    new_value: int


class RsaAccumulatorBackend(Protocol):
    name: str

    def hash_to_prime(self, hash_hex: str) -> int:
        ...

    def hash_to_prime_with_nonce(self, hash_hex: str, nonce: int = 0) -> HashPrimeResult:
        ...

    def generate_modulus(self) -> int:
        ...

    def generate_generator(self, modulus_n: int) -> int:
        ...

    def derive_base(self, modulus_n: int, start_counter: int = 0) -> tuple[int, int]:
        ...

    def add(self, current_value: int, element: int, modulus_n: int) -> int:
        ...

    def verify(self, witness: int, element: int, state_value: int, modulus_n: int) -> bool:
        ...


class InternalRsaAccumulatorBackend:
    name = "internal-rsa-accumulator"

    def hash_to_prime(self, hash_hex: str) -> int:
        return self.hash_to_prime_with_nonce(hash_hex).prime

    def hash_to_prime_with_nonce(self, hash_hex: str, nonce: int = 0) -> HashPrimeResult:
        current_nonce = nonce
        while True:
            candidate = int(
                hashlib.sha256(
                    f"{H2P_DOMAIN}:{hash_hex}:{current_nonce}".encode("ascii")
                ).hexdigest(),
                16,
            )
            candidate |= 1

            if _is_probable_prime(candidate):
                return HashPrimeResult(prime=candidate, nonce=current_nonce)

            current_nonce += 1

    def generate_modulus(self) -> int:
        # Retorna o módulo RSA-2048 de fatoração publicamente desconhecida.
        # Nenhuma das partes (incluindo o servidor) conhece p e q,
        # satisfazendo a premissa de ordem desconhecida do acumulador RSA.
        return RSA_2048_CHALLENGE_N

    def derive_base(self, modulus_n: int, start_counter: int = 0) -> tuple[int, int]:
        """
        Base pública do acumulador derivada DETERMINISTICAMENTE dos parâmetros
        do sistema, em vez de sorteada. A partir de um contador público, deriva
        um valor h por SHA-256 com separação de domínio ligada ao módulo N;
        exige gcd(h, N) = 1 e define:

            g = h² mod N

        garantindo que g seja um resíduo quadrático — o que evita elementos de
        ordem baixa (como o subgrupo gerado por -1) — e rejeitando os valores
        triviais 0 e 1. Caso alguma condição falhe, o contador é incrementado e
        a derivação é repetida.

        Retorna ``(g, contador)``: o contador é publicado como parâmetro do
        acumulador para que um verificador externo reproduza g sem precisar
        repetir o laço de derivação.
        """
        counter = start_counter
        n_bytes = (modulus_n.bit_length() + 7) // 8
        modulus_bytes = modulus_n.to_bytes(n_bytes, "big")
        while True:
            digest = hashlib.sha256(
                f"{ACCUMULATOR_BASE_DOMAIN}:".encode("ascii")
                + modulus_bytes
                + f":{counter}".encode("ascii")
            ).digest()
            h = int.from_bytes(digest, "big") % modulus_n
            if h > 1 and math.gcd(h, modulus_n) == 1:
                g = pow(h, 2, modulus_n)
                if g not in (0, 1):
                    return g, counter
            counter += 1

    def generate_generator(self, modulus_n: int) -> int:
        base, _ = self.derive_base(modulus_n)
        return base

    def add(self, current_value: int, element: int, modulus_n: int) -> int:
        return pow(current_value, element, modulus_n)

    def verify(self, witness: int, element: int, state_value: int, modulus_n: int) -> bool:
        return pow(witness, element, modulus_n) == state_value


class RsaAccumulatorAdapter:
    def __init__(self, backend: RsaAccumulatorBackend | None = None):
        self.backend = backend or InternalRsaAccumulatorBackend()

    @property
    def backend_name(self) -> str:
        return self.backend.name

    def generate_initial_parameters(self) -> tuple[int, int, int]:
        modulus_n = self.backend.generate_modulus()
        generator, base_counter = self.backend.derive_base(modulus_n)
        return generator, modulus_n, base_counter

    def accumulate(
        self,
        current_value: int,
        hash_hex: str,
        modulus_n: int,
    ) -> AccumulatorComputation:
        hash_prime = self.backend.hash_to_prime_with_nonce(hash_hex)
        x_value = hash_prime.prime
        new_value = self.backend.add(current_value, x_value, modulus_n)

        return AccumulatorComputation(
            x_value=x_value,
            x_nonce=hash_prime.nonce,
            new_value=new_value,
        )

    def verify_membership(
        self,
        witness: int,
        element: int,
        state_value: int,
        modulus_n: int,
    ) -> bool:
        return self.backend.verify(
            witness=witness,
            element=element,
            state_value=state_value,
            modulus_n=modulus_n,
        )


def _miller_rabin_round(value: int, d: int, s: int, base: int) -> bool:
    x = pow(base, d, value)
    if x == 1 or x == value - 1:
        return True
    for _ in range(s - 1):
        x = pow(x, 2, value)
        if x == value - 1:
            return True
    return False


def _is_probable_prime(value: int) -> bool:
    if value < 2:
        return False

    small_primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    if value in small_primes:
        return True
    if any(value % prime == 0 for prime in small_primes):
        return False

    d = value - 1
    s = 0
    while d % 2 == 0:
        s += 1
        d //= 2

    for base in small_primes:
        if base >= value:
            continue
        if not _miller_rabin_round(value, d, s, base):
            return False

    for _ in range(8):
        base = secrets.randbelow(value - 3) + 2
        if not _miller_rabin_round(value, d, s, base):
            return False

    return True


rsa_accumulator_adapter = RsaAccumulatorAdapter()
