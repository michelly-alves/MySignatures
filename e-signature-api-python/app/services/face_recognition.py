import cv2
import numpy as np
from insightface.app import FaceAnalysis

_face_app = None


def get_face_app():
    global _face_app
    if _face_app is None:
        _face_app = FaceAnalysis(name="buffalo_l")
        _face_app.prepare(ctx_id=0)
    return _face_app


def extract_face_embedding_from_path(image_path: str) -> np.ndarray:
    img = cv2.imread(image_path)

    if img is None:
        raise ValueError("Imagem inválida ou não encontrada")

    face_app = get_face_app()
    faces = face_app.get(img)

    if not faces:
        raise ValueError("Nenhum rosto detectado")

    return faces[0].embedding

def extract_face_embedding_from_bytes(image_bytes: bytes) -> np.ndarray:
    np_img = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError("Imagem inválida")

    face_app = get_face_app()
    faces = face_app.get(img)

    if not faces:
        raise ValueError("Nenhum rosto detectado")

    return faces[0].embedding


def extract_face_pose_from_bytes(image_bytes: bytes) -> float:
    """
    Retorna o ângulo de yaw (rotação horizontal) da face em graus.

    Usa face.pose[0] do InsightFace (buffalo_l com modelo 1k3d68).
    Fallback para estimativa via landmarks de 5 pontos se pose não estiver
    disponível (modelos mais leves).

    Convenção: yaw > 0 = face virada para a direita da câmera,
                yaw < 0 = face virada para a esquerda da câmera.

    Lança ValueError se nenhum rosto for detectado ou a imagem for inválida.
    """
    np_img = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Imagem inválida")

    face_app = get_face_app()
    faces = face_app.get(img)
    if not faces:
        raise ValueError("Nenhum rosto detectado no frame")

    face = faces[0]

    if getattr(face, "pose", None) is not None:
        return float(face.pose[0])

    kps = face.kps
    left_x = float(kps[0][0])
    right_x = float(kps[1][0])
    nose_x = float(kps[2][0])
    eye_span = right_x - left_x
    if eye_span < 1:
        return 0.0
    ratio = (nose_x - left_x) / eye_span
    return (0.5 - ratio) * 90.0  


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