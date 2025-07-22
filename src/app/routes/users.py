from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.config.database import get_db
from ..db.objects.repositories.users import UsersRepository
from ..db.objects.schemas.users import UsersCreate, UsersUpdate, UsersInDB
from typing import List
from uuid import UUID
from ..common.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=UsersInDB, status_code=status.HTTP_201_CREATED)
async def create_user(
    user: UsersCreate,
    db: AsyncSession = Depends(get_db)
):
    repository = UsersRepository(db)
    db_user = await repository.get_by_email(email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return await repository.create(user)

@router.get("/{user_id}", response_model=UsersInDB)
async def read_user(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    repository = UsersRepository(db)
    db_user = await repository.get_by_id(user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

@router.get("/clerk/{clerk_id}", response_model=UsersInDB)
async def get_user_by_clerk_id(
    clerk_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a user profile by Clerk ID."""
    repository = UsersRepository(db)
    user = await repository.get_by_clerk_id(clerk_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

@router.put("/{user_id}", response_model=UsersInDB)
async def update_user(
    user_id: int,
    user: UsersUpdate,
    db: AsyncSession = Depends(get_db)
):
    repository = UsersRepository(db)
    db_user = await repository.update(user_id=user_id, user=user)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

