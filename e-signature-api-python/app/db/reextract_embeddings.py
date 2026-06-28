import json
import sys

import cv2
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.services.face_recognition import (
    get_face_app,
    _select_primary_face,
    MIN_DET_SCORE,
)


def _sync_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg"):
        return url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def reextract(dry_run: bool = False) -> None:
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL nao configurada (verifique o .env).")

    face_app = get_face_app(high_res=True)
    engine = create_engine(_sync_url(settings.DATABASE_URL), future=True)

    ok = skipped = failed = 0
    low_quality: list[str] = []

    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT signer_id, full_name, photo_id_url FROM signer "
            "WHERE deleted_at IS NULL AND photo_id_url IS NOT NULL "
            "ORDER BY signer_id"
        )).fetchall()

        print(f"Signatarios a processar: {len(rows)}\n")

        for signer_id, full_name, photo_path in rows:
            img = cv2.imread(photo_path)
            if img is None:
                print(f"[FALHA ] #{signer_id} {full_name}: foto nao encontrada ({photo_path})")
                failed += 1
                continue

            faces = face_app.get(img)
            if not faces:
                print(f"[FALHA ] #{signer_id} {full_name}: nenhum rosto detectado")
                failed += 1
                continue

            face = _select_primary_face(faces)
            det_score = float(getattr(face, "det_score", 1.0))
            x1, y1, x2, y2 = face.bbox
            face_px = int(max(x2 - x1, y2 - y1))
            h, w = img.shape[:2]
            face_ratio = face_px / max(h, w)

            flag = ""
            if det_score < MIN_DET_SCORE:
                flag = "  <-- QUALIDADE BAIXA: troque a foto"
                low_quality.append(f"#{signer_id} {full_name}")

            print(
                f"[{'DRY' if dry_run else 'OK  '}] #{signer_id} {full_name}: "
                f"det_score={det_score:.3f} | rosto={face_px}px "
                f"({face_ratio:.0%} da imagem) | n_faces={len(faces)}{flag}"
            )

            if not dry_run:
                conn.execute(
                    text("UPDATE signer SET face_embedding = CAST(:emb AS jsonb), "
                         "updated_at = now() WHERE signer_id = :id"),
                    {"emb": json.dumps(face.embedding.tolist()), "id": signer_id},
                )
            ok += 1

    engine.dispose()

    print(
        f"\nResumo: {ok} processado(s)"
        f"{' (dry-run, nada gravado)' if dry_run else ' atualizado(s)'}"
        f", {failed} falha(s)."
    )
    if low_quality:
        print("Fotos com qualidade baixa (recomenda-se novo enrollment):")
        for s in low_quality:
            print("  -", s)


if __name__ == "__main__":
    reextract(dry_run="--dry-run" in sys.argv)
