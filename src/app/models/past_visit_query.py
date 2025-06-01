from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
from enum import Enum

class VisitTimeframe(str, Enum):
    LAST_MONTH = "last_month"
    LAST_3_MONTHS = "last_3_months"
    LAST_6_MONTHS = "last_6_months"
    LAST_YEAR = "last_year"
    SPECIFIC_DATE = "specific_date"
    DATE_RANGE = "date_range"
    ALL = "all"

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

class PastVisitQuery(BaseModel):
    """
    A structured query model for filtering and retrieving past visit information.
    """
    provider_name: Optional[str] = Field(None, description="Name of the healthcare provider to filter by")
    npi: Optional[str] = Field(None, description="NPI of the healthcare provider to filter by")
    timeframe: VisitTimeframe = Field(VisitTimeframe.ALL, description="Timeframe to filter visits by")
    start_date: Optional[date] = Field(None, description="Start date for date range queries")
    end_date: Optional[date] = Field(None, description="End date for date range queries")
    purpose: Optional[str] = Field(None, description="Filter by visit purpose (e.g., 'physical', 'follow-up')")
    location: Optional[str] = Field(None, description="Filter by visit location")
    sort_by: str = Field("date", description="Field to sort results by (e.g., 'date', 'provider')")
    sort_order: SortOrder = Field(SortOrder.DESC, description="Sort order (ascending or descending)")
    limit: Optional[int] = Field(None, description="Maximum number of results to return")

    class Config:
        json_schema_extra = {
            "example": {
                "provider_name": "Dr. Sarah Johnson",
                "timeframe": "last_6_months",
                "sort_by": "date",
                "sort_order": "desc",
                "limit": 5
            }
        } 