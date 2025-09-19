# Medical Citations Implementation

## Overview

This document describes the implementation of citation functionality for medical intent responses in the Care Capture FastAPI application. The solution uses separate response classes to minimize code changes across the codebase.

## Design Decision

**Problem**: Need to add citation details for medical-related responses only, while keeping other intents unchanged.

**Solution**: Create separate response classes for medical intents instead of modifying the common `IntentAiResponse` class.

## Implementation Details

### 1. New Response Classes

Created two new classes in `src/app/models/intent_identify.py`:

```python
class MedicalIntentAiResponse(GenericModel, Generic[T]):
    """Specialized response class for medical intents that includes citations."""
    type: str = "text"
    content: str
    citation: str  # Required citation field for medical responses
    data: T

class MedicalIntentResponse(GenericModel, Generic[T]):
    """
    Represents the response from medical intent handlers.
    
    Attributes:
        intent: The identified intent (should be MEDICAL_INQUIRY)
        responses: The responses with citations
    """
    intent: RouterOptions
    responses: List[MedicalIntentAiResponse[T]]
```

### 2. Updated Medical Inquiry Chain

Modified `src/app/chains/ai_chat_intents/medical_inquiry_intent/chain.py`:

- Changed return type from `IntentResponse[None]` to `MedicalIntentResponse[None]`
- Updated to use `MedicalIntentAiResponse` instead of `IntentAiResponse`
- Added citation parsing functionality
- Citations are now required (no longer optional)

### 3. Enhanced Prompt System

Updated `src/app/chains/ai_chat_intents/medical_inquiry_intent/constants.py`:

- Added specific citation guidelines
- Structured response format with `RESPONSE:` and `CITATIONS:` sections
- Instructions for proper medical source citation

### 4. Router Updates

Modified `src/app/chains/ai_chat_intents/intend_identifier/router.py`:

- Updated return type to `Union[IntentResponse, MedicalIntentResponse]`
- Medical inquiry handler now returns `MedicalIntentResponse`
- Other handlers continue to use `IntentResponse`

### 5. Citation Parsing

Added `_parse_medical_response()` method in the medical inquiry chain:

- Parses structured LLM responses
- Extracts content and citations separately
- Provides fallback citations when parsing fails
- Handles multiple citation sources

## Benefits of This Approach

1. **Minimal Code Changes**: Only medical intent code was modified
2. **Type Safety**: Clear separation between medical and non-medical responses
3. **Backward Compatibility**: Existing intent handlers remain unchanged
4. **Future Flexibility**: Easy to add citations to other intents if needed
5. **Clear Intent**: Medical responses explicitly require citations

## Usage Examples

### Medical Intent Response (with citations)
```python
response = MedicalIntentResponse[None](
    intent=RouterOptions.MEDICAL_INQUIRY,
    responses=[
        MedicalIntentAiResponse(
            type="text",
            content="High blood pressure affects millions...",
            citation="Source: American Heart Association - https://www.heart.org/...",
            data=None
        )
    ]
)
```

### Regular Intent Response (no citations)
```python
response = IntentResponse[None](
    intent=RouterOptions.PAST_VISITS,
    responses=[
        IntentAiResponse(
            type="text",
            content="Your appointment was on...",
            data=None
        )
    ]
)
```

## Testing

The implementation includes comprehensive tests that verify:

1. Medical response structure with citations
2. Regular response structure without citations
3. Citation parsing functionality
4. Proper separation between response types

## Future Considerations

- If other intents need citations in the future, they can either:
  - Use the existing `MedicalIntentResponse` classes
  - Create their own specialized response classes
  - Modify the common classes if citations become universal

This approach provides maximum flexibility while maintaining code clarity and minimizing impact on existing functionality. 