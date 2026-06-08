"""Initial

Revision ID: eda50a4d0553
Revises: 
Create Date: 2026-01-03 16:26:23.490884

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'eda50a4d0553'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
def upgrade() -> None:
    # --------------------------
    # Tabelas básicas
    # --------------------------
    op.create_table(
        'user_account',
        sa.Column('user_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('password_hash', sa.CHAR(60), nullable=True),
        sa.Column('role', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('deleted_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('face_embedding', postgresql.BYTEA(), nullable=True)
    )
    op.create_index(op.f('user_account_email_idx'), 'user_account', ['email'], unique=True, postgresql_where='(deleted_at IS NULL)')

    op.create_table(
        'company',
        sa.Column('company_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('legal_name', sa.String(255), nullable=False),
        sa.Column('tax_id', sa.CHAR(14), nullable=False, unique=True),
        sa.Column('contact_email', sa.String(255), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('deleted_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user_account.user_id'], ondelete='CASCADE')
    )

    # --------------------------
    # Signers e status
    # --------------------------
    op.create_table(
        'document_status',
        sa.Column('status_id', sa.Integer(), primary_key=True),
        sa.Column('description', sa.String(50), nullable=False)
    )

    op.create_table(
        'signer',
        sa.Column('signer_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('national_id', sa.String(255), nullable=False, unique=True),
        sa.Column('phone_number', sa.String(20), nullable=False),
        sa.Column('contact_email', sa.String(255), nullable=False),
        sa.Column('public_key', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('deleted_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('photo_id_url', sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user_account.user_id'], ondelete='SET NULL')
    )

    # --------------------------
    # Documentos e relacionamentos
    # --------------------------
    op.create_table(
        'document',
        sa.Column('document_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('hash_sha256', sa.CHAR(64), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('deleted_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['company.company_id'], ondelete='CASCADE')
    )

    op.create_table(
        'document_signer',
        sa.Column('doc_sign_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('document_id', sa.BigInteger(), nullable=False),
        sa.Column('signer_id', sa.BigInteger(), nullable=False),
        sa.Column('sign_order', sa.Integer(), nullable=True, server_default=sa.text('1')),
        sa.Column('status_id', sa.Integer(), nullable=False),
        sa.Column('authenticated_at', postgresql.TIMESTAMP(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('signed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['document.document_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['signer_id'], ['signer.signer_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['status_id'], ['document_status.status_id'])
    )

    op.create_table(
        'digital_signature',
        sa.Column('signature_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('doc_sign_id', sa.BigInteger(), nullable=False),
        sa.Column('signer_id', sa.BigInteger(), nullable=False),
        sa.Column('signature_data', sa.Text(), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('signed_at', postgresql.TIMESTAMP(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['doc_sign_id'], ['document_signer.doc_sign_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['signer_id'], ['signer.signer_id'], ondelete='CASCADE')
    )

    # --------------------------
    # Accumulator
    # --------------------------
    op.create_table(
        'accumulator_state',
        sa.Column('state_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('previous_state_id', sa.BigInteger(), nullable=True),
        sa.Column('state_value_hex', sa.Text(), nullable=False),
        sa.Column('generator_hex', sa.Text(), nullable=False),
        sa.Column('modulus_n_hex', sa.Text(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['previous_state_id'], ['accumulator_state.state_id'], ondelete='SET NULL')
    )

    op.create_table(
        'accumulator_element',
        sa.Column('element_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('document_id', sa.BigInteger(), nullable=False),
        sa.Column('signature_id', sa.BigInteger(), nullable=True),
        sa.Column('hash_hex', sa.CHAR(64), nullable=False),
        sa.Column('x_value_hex', sa.Text(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['document.document_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['signature_id'], ['digital_signature.signature_id'], ondelete='SET NULL')
    )
    op.create_index(op.f('idx_accumulator_hash'), 'accumulator_element', ['hash_hex'], unique=False)

    op.create_table(
        'accumulator_element_state',
        sa.Column('element_id', sa.BigInteger(), nullable=False),
        sa.Column('state_id', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['element_id'], ['accumulator_element.element_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['state_id'], ['accumulator_state.state_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('element_id'),
        sa.UniqueConstraint('element_id', 'state_id')
    )

    op.create_table(
        'witness',
        sa.Column('witness_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('element_id', sa.BigInteger(), nullable=False),
        sa.Column('state_id', sa.BigInteger(), nullable=False),
        sa.Column('witness_value_hex', sa.Text(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('is_valid', sa.Boolean(), nullable=True),
        sa.Column('validated_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['element_id'], ['accumulator_element.element_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['state_id'], ['accumulator_state.state_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('element_id')
    )

    # --------------------------
    # Identity, reset password & logs
    # --------------------------
    op.create_table(
        'reset_password_tokens',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('token', sa.String(64), nullable=False, unique=True),
        sa.Column('expires_at', postgresql.TIMESTAMP(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user_account.user_id'], ondelete='CASCADE')
    )

    op.create_table(
        'identity_document',
        sa.Column('identity_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('signer_id', sa.BigInteger(), nullable=False),
        sa.Column('document_type', sa.Integer(), nullable=False),
        sa.Column('document_number', sa.String(50), nullable=True),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('mime_type', sa.String(50), nullable=True),
        sa.Column('file_hash', sa.CHAR(64), nullable=False),
        sa.Column('validation_status', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('deleted_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['signer_id'], ['signer.signer_id'], ondelete='CASCADE')
    )

    op.create_table(
        'audit_log',
        sa.Column('audit_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('entity_name', sa.String(100), nullable=False),
        sa.Column('entity_id', sa.BigInteger(), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'))
    )
    op.create_index(op.f('idx_audit_entity'), 'audit_log', ['entity_name', 'entity_id'], unique=False)

    op.create_table(
        'public_accumulator_registry',
        sa.Column('registry_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('state_id', sa.BigInteger(), nullable=False),
        sa.Column('published_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('source', sa.String(100), nullable=True, server_default=sa.text("'internal'::character varying")),
        sa.ForeignKeyConstraint(['state_id'], ['accumulator_state.state_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('state_id')
    )

    op.create_table(
        'auth_log',
        sa.Column('log_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('mfa_type', sa.Integer(), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=True, server_default=sa.text('1')),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('logged_at', postgresql.TIMESTAMP(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('user_id', sa.BigInteger(), nullable=False)
    )

    op.create_table(
        'otp_codes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email', sa.Text(), nullable=False, unique=True),
        sa.Column('phone_number', sa.String(20), nullable=True),
        sa.Column('code', sa.String(6), nullable=False),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=True, server_default=sa.text('now()'))
    )


def downgrade() -> None:
    """Drop all tables in reverse order"""
    op.drop_table('signer')
    op.drop_table('document')
    op.drop_table('document_status')
    op.drop_table('user_account')
    op.drop_table('company')