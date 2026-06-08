from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from passlib.hash import bcrypt
import re

from app.models.user import User, Role
from app.models.signer import Signer
from app.schemas.user import CreateUser, UpdateUser
from app.models.company import Company
from app.security.password import hash_password
from fastapi import status

def _create_company(user: User, data: CreateUser, db: AsyncSession) -> None:
    if not data.legal_name or not data.tax_id:
        raise ValueError(
            "Os campos 'legal_name' e 'tax_id' são obrigatórios para empresas"
        )
    if not data.phone_number:
        raise ValueError("O campo 'phone_number' é obrigatório para empresas")

    company = Company(
        legal_name=data.legal_name,
        tax_id=re.sub(r'\D', '', data.tax_id),
        email=data.email,
        phone_number=data.phone_number,
        user_id=user.user_id
    )
    db.add(company)

def _create_signer(user: User, data: CreateUser, db: AsyncSession) -> None:
    if not data.full_name:
        raise ValueError("O campo 'full_name' é obrigatório para signatários")
    if not data.phone_number:
        raise ValueError("O campo 'phone_number' é obrigatório para signatários")
    if not data.national_id:
        raise ValueError("O campo 'national_id' é obrigatório para signatários")

    signer = Signer(
        full_name=data.full_name,
        phone_number=data.phone_number,
        national_id=re.sub(r'\D', '', data.national_id),
        contact_email=data.email,
        user_id=user.user_id
    )
    db.add(signer)


async def create_user(db: AsyncSession, data: CreateUser) -> User:
    if not data.email:
        raise ValueError("O campo 'email' é obrigatório")
    if not data.password:
        raise ValueError("O campo 'password' é obrigatório")
    if data.role is None:
        raise ValueError("O campo 'role' é obrigatório")

    # Verifica duplicidade de e-mail
    result = await db.execute(
        select(User).where(User.email == data.email)
    )
    if result.scalars().first():
        raise ValueError("Já existe um usuário cadastrado com este e-mail")

    # Valida role antes de qualquer operação no banco
    if data.role not in (Role.COMPANY, Role.SIGNER, Role.ADMIN):
        raise ValueError("Tipo de usuário inválido. Use COMPANY, SIGNER ou ADMIN")

    if data.role == Role.COMPANY:
        tax_id = re.sub(r'\D', '', data.tax_id or "")
        result = await db.execute(
            select(Company).where(
                Company.tax_id == tax_id,
                Company.deleted_at.is_(None),
            )
        )
        if result.scalar_one_or_none():
            raise ValueError("Já existe uma empresa cadastrada com este CNPJ")

    if data.role == Role.SIGNER:
        national_id = re.sub(r'\D', '', data.national_id or "")
        result = await db.execute(
            select(Signer).where(
                Signer.national_id == national_id,
                Signer.deleted_at.is_(None),
            )
        )
        if result.scalar_one_or_none():
            raise ValueError("Já existe um signatário cadastrado com este CPF")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password) if data.password else None,
        role=int(data.role)
    )
    db.add(user)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("O e-mail já está em uso") 

    try:
        if data.role == Role.COMPANY:
            _create_company(user, data, db)
            user.is_active = True
        elif data.role == Role.SIGNER:
            _create_signer(user, data, db)
        elif data.role == Role.ADMIN:
            user.is_active = True

        await db.commit()
        await db.refresh(user)
        return user

    except ValueError:
        await db.rollback()
        raise 

    except IntegrityError:
        await db.rollback()
        raise ValueError(
            "Não foi possível cadastrar: e-mail, CNPJ ou CPF já está em uso"
        )

    except Exception:
        await db.rollback()
        raise 
    
    
async def get_all_users(db: AsyncSession):
    result = await db.execute(
        select(User).where(User.deleted_at.is_(None))
    )
    return result.scalars().all()


async def get_user_by_id(db: AsyncSession, user_id: int):
    result = await db.execute(
        select(User)
        .where(User.user_id == user_id)
        .where(User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def get_full_user_profile(db: AsyncSession, user: User) -> dict:

    user_data = {
        "user_id": user.user_id,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "otp_verified_at": user.otp_verified_at,
        "requires_otp_verification": user.role == Role.SIGNER and user.otp_verified_at is None,
        "created_at": user.created_at,
    }

    if user.role == Role.COMPANY or user.role == 0:
        result = await db.execute(
            select(Company)
            .where(
                Company.user_id == user.user_id,
                Company.deleted_at.is_(None),
            )
            .order_by(Company.company_id.desc())
        )
        company = result.scalars().first()
        if company:
            user_data.update({
                "company_id": company.company_id,
                "name": company.legal_name,
                "legal_name": company.legal_name,
                "tax_id": company.tax_id,
                "contact_email": company.email,
                "phone_number": company.phone_number,
            })

    elif user.role == Role.SIGNER or user.role == 2:
        result = await db.execute(
            select(Signer)
            .where(
                Signer.user_id == user.user_id,
                Signer.deleted_at.is_(None),
            )
            .order_by(Signer.signer_id.desc())
        )
        signer = result.scalars().first()
        if signer:
            user_data.update({
                "signer_id": signer.signer_id,
                "name": signer.full_name,
                "full_name": signer.full_name,
                "phone_number": signer.phone_number,
                "contact_email": signer.contact_email,
                "national_id": signer.national_id,
                "photo_id_url": signer.photo_id_url,
                "has_signing_key": signer.public_key is not None,
            })

    return user_data


async def update_user(
    db: AsyncSession,
    user_id: int,
    data: UpdateUser
):
    result = await db.execute(select(User).where(User.user_id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()

    if not user:
        return None

    if data.email:
        user.email = data.email
    if data.role is not None:
        user.role = int(data.role)

    user.updated_at = datetime.utcnow()

    if user.role == 1: 
        pass

    elif user.role == 2:  
        result = await db.execute(
            select(Signer)
            .where(Signer.user_id == user.user_id, Signer.deleted_at.is_(None))
            .order_by(Signer.signer_id.desc())
        )
        signer = result.scalars().first()
        if signer:
            full_name = data.full_name or data.name
            if full_name:
                signer.full_name = full_name
            if data.contact_email:
                signer.contact_email = data.contact_email
            if data.phone_number:
                signer.phone_number = data.phone_number
            if data.national_id:
                signer.national_id = data.national_id
            signer.updated_at = datetime.utcnow()

    elif user.role == 0:  
        result = await db.execute(
            select(Company)
            .where(Company.user_id == user.user_id, Company.deleted_at.is_(None))
            .order_by(Company.company_id.desc())
        )
        company = result.scalars().first()
        if company:
            if data.legal_name:
                company.legal_name = data.legal_name
            if data.contact_email or data.email:
                company.email = data.contact_email or data.email
            if data.phone_number:
                company.phone_number = data.phone_number
            if data.tax_id:
                company.tax_id = re.sub(r'\D', '', data.tax_id)
            company.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(user)

    return user


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    user = await get_user_by_id(db, user_id)
    if not user:
        return False

    deleted_at = datetime.utcnow()

    user.is_active = False
    user.updated_at = deleted_at
    user.deleted_at = deleted_at

    if user.role == Role.SIGNER or user.role == 2:
        result = await db.execute(
            select(Signer).where(
                Signer.user_id == user.user_id,
                Signer.deleted_at.is_(None),
            )
        )
        for signer in result.scalars().all():
            signer.updated_at = deleted_at
            signer.deleted_at = deleted_at

    elif user.role == Role.COMPANY or user.role == 0:
        result = await db.execute(
            select(Company).where(
                Company.user_id == user.user_id,
                Company.deleted_at.is_(None),
            )
        )
        for company in result.scalars().all():
            company.updated_at = deleted_at
            company.deleted_at = deleted_at

    await db.commit()
    return True
