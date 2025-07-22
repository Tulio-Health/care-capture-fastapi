from pydantic import BaseModel, Field
from typing import Optional, List

class Provider(BaseModel):
    id: str
    npi: str
    last_name: Optional[str] = Field(alias="lastName")
    first_name: str = Field(alias="firstName")
    middle_name: Optional[str] = Field(alias="middleName")
    suffix: Optional[str]
    gender: Optional[str]
    credentials: Optional[str]
    primary_specialty: Optional[str] = Field(alias="primarySpecialty")
    secondary_specialties: List[str] = Field(alias="secondarySpecialties")
    group_practice_name: str = Field(alias="groupPracticeName")
    address_line1: str = Field(alias="addressLine1")
    address_line2: Optional[str] = Field(alias="addressLine2")
    city: str
    state: Optional[str]
    zip_code: str = Field(alias="zipCode")
    phone_number: str = Field(alias="phoneNumber")

class ScheduleVisitRequest(BaseModel):
    text: str
    providers: Optional[List[Provider]] = []

class ScheduleVisitResponse(BaseModel):
    provider_id: Optional[str] = Field(alias="providerId")
    appointment_date: Optional[str] = Field(alias="appointmentDate")
    appointment_time: Optional[str] = Field(alias="appointmentTime")
    duration_minutes: Optional[int] = Field(alias="durationMinutes")
    purpose: Optional[str]
    location: Optional[str]
    status: Optional[str]
    provider_first_name: Optional[str] = Field(alias="providerFirstName")
    provider_last_name: Optional[str] = Field(alias="providerLastName")
    provider_specialty: Optional[str] = Field(alias="providerSpecialty")
    provider_address: Optional[str] = Field(alias="providerAddress")
    provider_phone: Optional[str] = Field(alias="providerPhone")