import asyncio
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.app.db.config.database import get_db
from src.app.db.objects.entities.patient_health_insights import PatientHealthInsights

async def debug_health_insights(user_id_str: str):
    """Debug function to test health insights query"""
    print(f"Testing with user_id: {user_id_str}")
    
    # Test UUID conversion
    try:
        user_id_uuid = UUID(user_id_str) if isinstance(user_id_str, str) else user_id_str
        print(f"Converted to UUID: {user_id_uuid} (type: {type(user_id_uuid)})")
    except Exception as e:
        print(f"UUID conversion error: {e}")
        return
    
    # Test database query
    async for db in get_db():
        try:
            # First, let's see all health insights in the table
            all_stmt = select(PatientHealthInsights)
            all_result = await db.execute(all_stmt)
            all_insights = all_result.scalars().all()
            print(f"Total health insights in database: {len(all_insights)}")
            
            for insight in all_insights:
                print(f"  - ID: {insight.id}, User ID: {insight.user_id} (type: {type(insight.user_id)})")
                print(f"    Insight data: {insight.insight_data}")
            
            # Now test the specific query
            health_insights_stmt = select(PatientHealthInsights).where(
                PatientHealthInsights.user_id == user_id_uuid
            )
            
            print(f"Query: {health_insights_stmt}")
            
            health_insights_result = await db.execute(health_insights_stmt)
            health_insights_orm = health_insights_result.scalars().all()
            
            print(f"Found {len(health_insights_orm)} health insights for user {user_id_str}")
            
            for insight in health_insights_orm:
                print(f"  - Insight ID: {insight.id}")
                print(f"  - User ID: {insight.user_id}")
                print(f"  - Insight Data: {insight.insight_data}")
                
        except Exception as e:
            print(f"Database query error: {e}")
        break

if __name__ == "__main__":
    # Test with the specific user_id
    test_user_id = "58ae6e54-c712-4900-bc02-f80a2f2d9e85"
    print(f"Testing with user_id: {test_user_id}")
    
    asyncio.run(debug_health_insights(test_user_id)) 