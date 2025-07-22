from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..entities.users import Users
from ..schemas.users import UsersCreate, UsersUpdate
from typing import Optional
from ....common.logging import get_logger

logger = get_logger(__name__)

class UsersRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user: UsersCreate) -> Users:
        db_user = Users(**user.model_dump())
        self.session.add(db_user)
        await self.session.commit()
        await self.session.refresh(db_user)
        return db_user

    async def get_by_id(self, user_id: str) -> Optional[Users]:
        
        logger.debug(f"Fetching user with ID: {user_id}")
        try:
            result = await self.session.execute(
                select(Users).where(Users.id == user_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching user with ID: {user_id}", exc_info=e)
            raise e
        

    async def get_by_email(self, email: str) -> Optional[Users]:
        result = await self.session.execute(
            select(Users).where(Users.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_clerk_id(self, clerk_id: str) -> Optional[Users]:
        result = await self.session.execute(
            select(Users).where(Users.clerk_id == clerk_id)
        )
        return result.scalar_one_or_none()
    
    async def get_all(self) -> Optional[Users]:
        result = await self.session.execute(
            select(Users)
        )
        return result.scalars().all()

    async def update(self, user_id: int, user: UsersUpdate) -> Optional[Users]:
        db_user = await self.get_by_id(user_id)
        if db_user:
            for key, value in user.model_dump(exclude_unset=True).items():
                setattr(db_user, key, value)
            await self.session.commit()
            await self.session.refresh(db_user)
        return db_user 