from fastapi import HTTPException

class CareCaptureError(HTTPException):
    """Base exception for care capture-related errors"""
    pass

class HealthCheckError(HTTPException):
    """Base exception for health check-related errors"""
    def __init__(self, care_capture_id=None):
        message = "Care capture health check not found" if care_capture_id is None else f"Care capture with id {care_capture_id} not found"
        super().__init__(status_code=404, detail=message)

class CareCaptureNotFoundError(CareCaptureError):
    """Exception raised when a care capture record is not found"""
    def __init__(self, care_capture_id=None):
        message = "Care capture not found" if care_capture_id is None else f"Care capture with id {care_capture_id} not found"
        super().__init__(status_code=404, detail=message)

class CareCaptureCreationError(CareCaptureError):
    """Exception raised when care capture creation fails"""
    def __init__(self, error: str):
        super().__init__(status_code=500, detail=f"Failed to create care capture: {error}") 