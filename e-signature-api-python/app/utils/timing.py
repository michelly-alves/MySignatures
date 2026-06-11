import logging
import time
from contextlib import contextmanager


@contextmanager
def log_duration(logger: logging.Logger, operation: str, **context):
    """
    Mede e registra o tempo de execução de um bloco de código.

    Uso:
        with log_duration(logger, "Cálculo do Hash do Documento", document_id=42):
            ...

    Emite ao final um log no formato:
        [TEMPO] Cálculo do Hash do Documento levou 12.34 ms | document_id=42
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        extra = "".join(f" | {key}={value}" for key, value in context.items())
        logger.info("[TEMPO] %s levou %.2f ms%s", operation, elapsed_ms, extra)


@contextmanager
def accumulate_duration(bucket: dict[str, float], key: str):
    """
    Soma o tempo de execução de um bloco em ``bucket[key]`` (em ms),
    acumulando com chamadas anteriores que usem a mesma chave.

    Diferente de `log_duration`, não emite log: serve para separar, dentro
    de uma operação maior, o tempo gasto em categorias distintas (ex.:
    cálculo criptográfico vs. I/O de banco) MESMO quando os blocos de cada
    categoria se intercalam. Ao final, quem chama loga o resumo do bucket.

    Uso:
        timings: dict[str, float] = {}
        with accumulate_duration(timings, "cripto"):
            ...
        with accumulate_duration(timings, "io_db"):
            ...
        logger.info("cripto=%.2f ms | io_db=%.2f ms", timings["cripto"], timings["io_db"])
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        bucket[key] = bucket.get(key, 0.0) + (time.perf_counter() - start) * 1000
