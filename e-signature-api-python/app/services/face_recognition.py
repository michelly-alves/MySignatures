import logging

import cv2
import numpy as np
from insightface.app import FaceAnalysis

logger = logging.getLogger(__name__)
_face_app = None
_face_app_highres = None

DET_SIZE = (640, 640)            # verificação ao vivo (rápido)
DET_SIZE_HIGHRES = (1024, 1024)  # enrollment (qualidade da referência)
MIN_DET_SCORE = 0.6


def get_face_app(high_res: bool = False):
    global _face_app, _face_app_highres
    if high_res:
        if _face_app_highres is None:
            app = FaceAnalysis(name="buffalo_l")
            app.prepare(ctx_id=0, det_size=DET_SIZE_HIGHRES)
            _face_app_highres = app
        return _face_app_highres

    if _face_app is None:
        app = FaceAnalysis(name="buffalo_l")
        app.prepare(ctx_id=0, det_size=DET_SIZE)
        _face_app = app
    return _face_app


def _select_primary_face(faces):
    return max(
        faces,
        key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
    )


def _embedding_from_image(img, *, source: str, high_res: bool = False) -> np.ndarray:
    if img is None:
        raise ValueError("Imagem inválida ou não encontrada")

    face_app = get_face_app(high_res=high_res)
    faces = face_app.get(img)
    if not faces:
        raise ValueError("Nenhum rosto detectado")

    face = _select_primary_face(faces)

    det_score = float(getattr(face, "det_score", 1.0))
    if det_score < MIN_DET_SCORE:
        logger.warning(
            "Qualidade baixa na deteccao facial | source=%s | det_score=%.3f | "
            "embedding pouco confiavel pode reduzir o score de comparacao.",
            source, det_score,
        )

    return face.embedding


def extract_face_embedding_from_path(image_path: str, high_res: bool = False) -> np.ndarray:
    return _embedding_from_image(cv2.imread(image_path), source="path", high_res=high_res)

MIN_ENROLL_FACE_PX = 120        # abaixo disso o alinhamento (112px) vira upscale
MIN_ENROLL_DET_SCORE = 0.50     # confiança mínima de detecção
ENROLL_BLUR_WARN_VAR = 15.0     # nitidez apenas para AVISO (não rejeita)


def extract_enrollment_embedding(image_path: str) -> np.ndarray:

    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Imagem inválida ou não encontrada")

    face_app = get_face_app(high_res=True)
    faces = face_app.get(img)
    if not faces:
        raise ValueError(
            "Nenhum rosto detectado na foto. Envie uma imagem nítida em que o "
            "rosto do documento apareça com clareza."
        )

    face = _select_primary_face(faces)
    x1, y1, x2, y2 = face.bbox
    face_px = int(max(x2 - x1, y2 - y1))
    det_score = float(getattr(face, "det_score", 1.0))

    if det_score < MIN_ENROLL_DET_SCORE:
        raise ValueError(
            f"A foto não tem qualidade suficiente para biometria "
            f"(confiança de detecção {det_score:.2f}). Envie uma imagem mais "
            "nítida e bem iluminada do documento."
        )

    if face_px < MIN_ENROLL_FACE_PX:
        raise ValueError(
            f"O rosto na foto está pequeno demais para biometria ({face_px}px). "
            "Tire a foto mais de perto, de modo que o rosto do documento fique "
            "maior e mais nítido no enquadramento."
        )

    try:
        crop = img[max(0, int(y1)):int(y2), max(0, int(x1)):int(x2)]
        if crop.size:
            blur_var = cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
            if blur_var < ENROLL_BLUR_WARN_VAR:
                logger.warning(
                    "Foto de enrollment com baixa nitidez | blur_var=%.1f | "
                    "pode reduzir a precisao da biometria.", blur_var,
                )
    except Exception:
        pass

    return face.embedding


def extract_face_embedding_from_bytes(image_bytes: bytes, high_res: bool = False) -> np.ndarray:
    np_img = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)
    return _embedding_from_image(img, source="bytes", high_res=high_res)


def _yaw_from_face(face) -> float:

    if getattr(face, "pose", None) is not None:
        return float(face.pose[1])

    kps = face.kps
    left_x = float(kps[0][0])
    right_x = float(kps[1][0])
    nose_x = float(kps[2][0])
    eye_span = right_x - left_x
    if eye_span < 1:
        return 0.0
    ratio = (nose_x - left_x) / eye_span
    return (0.5 - ratio) * 90.0


def _detect_single_face(image_bytes: bytes):
    """Decodifica a imagem e retorna a primeira face detectada (1 inferência)."""
    np_img = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Imagem inválida")

    face_app = get_face_app()
    faces = face_app.get(img)
    if not faces:
        raise ValueError("Nenhum rosto detectado no frame")
    return _select_primary_face(faces)


def extract_face_pose_from_bytes(image_bytes: bytes) -> float:

    return _yaw_from_face(_detect_single_face(image_bytes))


def extract_face_embedding_and_yaw_from_bytes(image_bytes: bytes) -> tuple[np.ndarray, float]:
    face = _detect_single_face(image_bytes)
    return face.embedding, _yaw_from_face(face)


def compare_embeddings(stored_embedding, selfie_embedding) -> float:
    a = np.array(stored_embedding, dtype=np.float32)
    b = np.array(selfie_embedding, dtype=np.float32)

    if a.ndim != 1 or b.ndim != 1:
        raise ValueError("Embedding inválido")

    if a.shape[0] != b.shape[0]:
        raise ValueError("Dimensão incompatível entre embeddings")

    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        raise ValueError("Embedding com norma zero")

    return float(np.dot(a, b) / denom)