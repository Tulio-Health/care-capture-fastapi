from uuid import UUID
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

class KeyPoints(BaseModel):
    points: List[str]

class Medication(BaseModel):
    name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None

class Diagnosis(BaseModel):
    condition: str
    status: Optional[str] = None

class Instruction(BaseModel):
    instruction: str
    category: str
    
class Recommendation(BaseModel):
    recommendation: str
    type: str

class HealthInsights(BaseModel):
    summary_text: str
    key_points: KeyPoints
    medications: List[Medication]
    diagnoses: List[Diagnosis]
    instructions: List[Instruction]
    recommendations: List[Recommendation]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class HealthInsightsRequest(BaseModel):
    user_id: UUID
    
from pydantic import BaseModel
from typing import List, Optional

class Condition(BaseModel):
    name: str
    details: Optional[str] = None
    date: str = None

class SurgeryProcedure(BaseModel):
    name: str 
    details: Optional[str] = None
    date: str = None

class Medication(BaseModel):
    name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    date: str = None

class PriorTest(BaseModel):
    name: str
    result: Optional[str] = None
    date: str = None

class HealthInsightsResponse(BaseModel):
    conditions: List[Condition] = []
    surgeriesAndProcedures: List[SurgeryProcedure] = []
    medications: List[Medication] = []
    priorTesting: List[PriorTest] = []