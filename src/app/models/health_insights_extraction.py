from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel
from typing import List, Optional
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
    summary_text: str = Field(..., alias="summaryText")
    key_points: KeyPoints = Field(..., alias="keyPoints")
    medications: List[Medication]
    diagnoses: List[Diagnosis]
    instructions: List[Instruction]
    recommendations: List[Recommendation]
    created_at: datetime = Field(..., alias="createdAt")
    
    model_config = ConfigDict(from_attributes=True)


class HealthInsightsRequest(BaseModel):
    user_id: UUID
    

class Condition(BaseModel):
    name: str
    details: Optional[str] = None
    date: Optional[str] = None

class SurgeryProcedure(BaseModel):
    name: str 
    details: Optional[str] = None
    date: Optional[str] = None

class Medication(BaseModel):
    name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    date: Optional[str] = None

class PriorTest(BaseModel):
    name: str
    result: Optional[str] = None
    date: Optional[str] = None

class HealthInsightsResponse(BaseModel):
    conditions: List[Condition] = []
    surgeriesAndProcedures: List[SurgeryProcedure] = []
    medications: List[Medication] = []
    priorTesting: List[PriorTest] = []
    
class GenerateHealthInsightsRequest(BaseModel):
    appointment_id: UUID
    user_id: UUID