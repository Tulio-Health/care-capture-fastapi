from fastapi import HTTPException

class CareCaptureError(HTTPException):
    """Base exception for care capture-related errors"""
    pass

class HealthCheckError(HTTPException):
    """Base exception for health check-related errors"""
    def __init__(self, care_capture_id=None):
        message = "Care capture health check not found" if care_capture_id is None else f"Care capture with id {care_capture_id} not found"
        super().__init__(status_code=404, detail=message)

# class CareCaptureNotFoundError(CareCaptureError):
#     def __init__(self, care_capture_id=None):
#         message = "Care capture not found" if care_capture_id is None else f"Care capture with id {care_capture_id} not found"
#         super().__init__(status_code=404, detail=message)

# class CareCaptureCreationError(CareCaptureError):
#     def __init__(self, error: str):
#         super().__init__(status_code=500, detail=f"Failed to create care capture: {error}")

# class UserError(HTTPException):
#     """Base exception for user-related errors"""
#     pass

# class UserNotFoundError(UserError):
#     def __init__(self, user_id=None):
#         message = "User not found" if user_id is None else f"User with id {user_id} not found"
#         super().__init__(status_code=404, detail=message)

# class PasswordMismatchError(UserError):
#     def __init__(self):
#         super().__init__(status_code=400, detail="New passwords do not match")

# class InvalidPasswordError(UserError):
#     def __init__(self):
#         super().__init__(status_code=401, detail="Current password is incorrect")

# class AuthenticationError(HTTPException):
#     def __init__(self, message: str = "Could not validate user"):
#         super().__init__(status_code=401, detail=message)
