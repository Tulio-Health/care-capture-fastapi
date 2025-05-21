from fastapi import APIRouter

from src.app.chains.schedule_visit.chain import ScheduleVisitChain
from src.app.models.schedule_visit import ScheduleVisitRequest, ScheduleVisitResponse


router = APIRouter(
    prefix="/care-capture/schedule-visit",
    tags=["care-capture-schedule-visit"]
)

@router.post('/',
             response_model=ScheduleVisitResponse,
             status_code=200)
async def schedule_visit(request:ScheduleVisitRequest):
    print(f"Schedule Visit Request: {request}")
    schedule_visit_chain = ScheduleVisitChain()
    response = schedule_visit_chain.schedule_visit(text=request.text, providers=request.providers)
    return response