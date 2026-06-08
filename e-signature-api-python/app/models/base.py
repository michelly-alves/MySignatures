from sqlalchemy.orm import declarative_base
from .user import User, Signer, ResetPasswordToken
from .document import Document
from .document_status import DocumentStatus
from .document_signer import DocumentSigner
from .face_verify import FaceVerifyRequest



Base = declarative_base()

