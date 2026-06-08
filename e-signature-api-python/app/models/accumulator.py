from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from app.db.base import Base


class AccumulatorState(Base):
    __tablename__ = "accumulator_state"

    state_id = Column(Integer, primary_key=True)
    previous_state_id = Column(Integer, ForeignKey("accumulator_state.state_id"), nullable=True)
    state_value_hex = Column(Text, nullable=False)
    generator_hex = Column(Text, nullable=False)
    modulus_n_hex = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(Integer, nullable=True)
    comments = Column(Text, nullable=True)


class AccumulatorElement(Base):
    __tablename__ = "accumulator_element"

    element_id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("document.document_id"), nullable=False)
    signature_id = Column(Integer, ForeignKey("digital_signature.signature_id"), nullable=True)
    hash_hex = Column(String(64), nullable=False)
    x_value_hex = Column(Text, nullable=False)
    x_nonce = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(Integer, nullable=True)


class AccumulatorElementState(Base):
    __tablename__ = "accumulator_element_state"

    element_id = Column(Integer, ForeignKey("accumulator_element.element_id"), primary_key=True)
    state_id = Column(Integer, ForeignKey("accumulator_state.state_id"), nullable=False)


class Witness(Base):
    __tablename__ = "witness"

    witness_id = Column(Integer, primary_key=True)
    element_id = Column(Integer, ForeignKey("accumulator_element.element_id"), nullable=False)
    state_id = Column(Integer, ForeignKey("accumulator_state.state_id"), nullable=False)
    witness_value_hex = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(Integer, nullable=True)
    is_valid = Column(Boolean, nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)


class PublicAccumulatorRegistry(Base):
    __tablename__ = "public_accumulator_registry"

    registry_id = Column(Integer, primary_key=True)
    state_id = Column(Integer, ForeignKey("accumulator_state.state_id"), nullable=False)
    published_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    source = Column(String(100), nullable=True, default="internal")
