from pydantic import BaseModel
from typing import Literal

class FaceVerifyRequest(BaseModel):
    live_image_base64: str


class LivenessFrame(BaseModel):
    step: Literal["front", "left", "right"]
    image_base64: str


class LivenessVerifyRequest(BaseModel):
    frames: list[LivenessFrame]
