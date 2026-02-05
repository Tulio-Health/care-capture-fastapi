# API Examples

This document provides practical code examples for using the Care Capture AI API endpoints in various programming languages.

---

## Table of Contents

1. [Comprehensive Summarization Endpoint](#comprehensive-summarization-endpoint)
2. [Transcript Summarization Endpoint](#transcript-summarization-endpoint)
3. [FHIR Analysis Endpoint](#fhir-analysis-endpoint)
4. [Querying Summaries (NodeAPI)](#querying-summaries-nodeapi)
5. [Error Handling](#error-handling)
6. [Advanced Usage](#advanced-usage)

---

## Comprehensive Summarization Endpoint

### cURL

```bash
# Both transcript and FHIR analysis in parallel
curl -X POST "https://api.example.com/care-capture/comprehensive-summary" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "appointment_id": "123e4567-e89b-12d3-a456-426614174000",
    "user_id": "223e4567-e89b-12d3-a456-426614174000",
    "transcripts": [
      {
        "text": "Patient presents with persistent headache for 3 days. Denies fever or neck stiffness. Vital signs stable.",
        "created_at": "2024-01-15T10:00:00Z",
        "language_code": "en"
      }
    ],
    "include_fhir_analysis": true,
    "resource_types": ["Condition", "Observation", "MedicationRequest"],
    "analysis_focus": "chronic_conditions",
    "timeout_seconds": 120
  }'
```

### Python

```python
import requests
from typing import List, Optional
from datetime import datetime

class CareCapture API:
    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_token}"
        }
    
    def comprehensive_summarization(
        self,
        appointment_id: str,
        user_id: str,
        transcripts: List[dict] = None,
        include_fhir_analysis: bool = False,
        resource_types: Optional[List[str]] = None,
        analysis_focus: Optional[str] = None,
        timeout_seconds: int = 120
    ):
        """
        Execute comprehensive summarization (parallel execution).
        
        Args:
            appointment_id: Appointment UUID
            user_id: User/patient UUID
            transcripts: List of transcript dicts with 'text', 'created_at', 'language_code'
            include_fhir_analysis: Enable FHIR analysis
            resource_types: FHIR resource types to include
            analysis_focus: Focus area (e.g., 'chronic_conditions')
            timeout_seconds: Max execution time (10-300)
            
        Returns:
            dict: Response with summaries, errors, and metrics
        """
        payload = {
            "appointment_id": appointment_id,
            "user_id": user_id,
            "timeout_seconds": timeout_seconds
        }
        
        if transcripts:
            payload["transcripts"] = transcripts
        if include_fhir_analysis:
            payload["include_fhir_analysis"] = True
        if resource_types:
            payload["resource_types"] = resource_types
        if analysis_focus:
            payload["analysis_focus"] = analysis_focus
        
        response = requests.post(
            f"{self.base_url}/care-capture/comprehensive-summary",
            json=payload,
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

# Usage
api = CareCaptureAPI(
    base_url="https://api.example.com",
    api_token="your_token_here"
)

result = api.comprehensive_summarization(
    appointment_id="123e4567-e89b-12d3-a456-426614174000",
    user_id="223e4567-e89b-12d3-a456-426614174000",
    transcripts=[
        {
            "text": "Patient presents with persistent headache...",
            "created_at": "2024-01-15T10:00:00Z",
            "language_code": "en"
        }
    ],
    include_fhir_analysis=True,
    resource_types=["Condition", "Observation", "MedicationRequest"],
    analysis_focus="chronic_conditions"
)

# Handle response
if result['metrics']['error_count'] == 0:
    print("Complete success!")
    for summary in result['summaries']:
        print(f"Source: {summary['metadata']['source']}")
        print(f"Summary: {summary['summary_text'][:100]}...")
elif result['metrics']['partial_success']:
    print(f"Partial success: {result['metrics']['success_count']} succeeded")
    print(f"Errors: {result['errors']}")
else:
    print("Complete failure")
    print(f"Errors: {result['errors']}")
```

### JavaScript/TypeScript

```typescript
interface Transcript {
  text: string;
  created_at?: string;
  language_code?: string;
}

interface ComprehensiveSummaryRequest {
  appointment_id: string;
  user_id: string;
  transcripts?: Transcript[];
  include_fhir_analysis?: boolean;
  resource_types?: string[];
  analysis_focus?: string;
  timeout_seconds?: number;
}

interface ComprehensiveSummaryResponse {
  summaries: Array<{
    id: string;
    appointment_id: string;
    user_id: string;
    summary_text: string;
    metadata: {
      source: 'transcript' | 'fhir_analysis';
      [key: string]: any;
    };
    created_at: string;
    updated_at: string;
  }>;
  errors: Array<{
    source: string;
    error_type: string;
    error_message: string;
    details?: string;
    timestamp: string;
  }>;
  metrics: {
    total_requested: number;
    success_count: number;
    error_count: number;
    execution_time_seconds: number;
    partial_success: boolean;
    timeout_occurred: boolean;
  };
}

class CareCaptureAPI {
  constructor(
    private baseUrl: string,
    private apiToken: string
  ) {}

  async comprehensiveSummarization(
    request: ComprehensiveSummaryRequest
  ): Promise<ComprehensiveSummaryResponse> {
    const response = await fetch(
      `${this.baseUrl}/care-capture/comprehensive-summary`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.apiToken}`
        },
        body: JSON.stringify(request)
      }
    );

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return response.json();
  }
}

// Usage
const api = new CareCaptureAPI(
  'https://api.example.com',
  'your_token_here'
);

const result = await api.comprehensiveSummarization({
  appointment_id: '123e4567-e89b-12d3-a456-426614174000',
  user_id: '223e4567-e89b-12d3-a456-426614174000',
  transcripts: [
    {
      text: 'Patient presents with persistent headache...',
      created_at: '2024-01-15T10:00:00Z',
      language_code: 'en'
    }
  ],
  include_fhir_analysis: true,
  resource_types: ['Condition', 'Observation', 'MedicationRequest'],
  analysis_focus: 'chronic_conditions',
  timeout_seconds: 120
});

// Handle response
if (result.metrics.error_count === 0) {
  console.log('Complete success!');
  result.summaries.forEach(summary => {
    console.log(`Source: ${summary.metadata.source}`);
    console.log(`Summary: ${summary.summary_text.substring(0, 100)}...`);
  });
} else if (result.metrics.partial_success) {
  console.log(`Partial success: ${result.metrics.success_count} succeeded`);
  console.error('Errors:', result.errors);
} else {
  console.error('Complete failure');
  console.error('Errors:', result.errors);
}
```

### React Component Example

```tsx
import React, { useState } from 'react';
import { CareCaptureAPI } from './api';

interface Props {
  appointmentId: string;
  userId: string;
}

export const ComprehensiveSummary: React.FC<Props> = ({ 
  appointmentId, 
  userId 
}) => {
  const [loading, setLoading] = useState(false);
  const [transcriptSummary, setTranscriptSummary] = useState<string | null>(null);
  const [fhirSummary, setFhirSummary] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);

  const generateSummary = async (transcriptText: string) => {
    setLoading(true);
    setErrors([]);

    try {
      const api = new CareCaptureAPI(
        process.env.REACT_APP_API_URL!,
        localStorage.getItem('authToken')!
      );

      const result = await api.comprehensiveSummarization({
        appointment_id: appointmentId,
        user_id: userId,
        transcripts: [{ text: transcriptText }],
        include_fhir_analysis: true,
        timeout_seconds: 120
      });

      // Extract summaries by source
      const transcript = result.summaries.find(
        s => s.metadata.source === 'transcript'
      );
      const fhir = result.summaries.find(
        s => s.metadata.source === 'fhir_analysis'
      );

      setTranscriptSummary(transcript?.summary_text || null);
      setFhirSummary(fhir?.summary_text || null);

      // Handle errors
      if (result.errors.length > 0) {
        setErrors(result.errors.map(e => e.error_message));
      }
    } catch (error) {
      setErrors([`Failed to generate summary: ${error.message}`]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="comprehensive-summary">
      {loading && <div className="spinner">Generating summaries...</div>}

      {errors.length > 0 && (
        <div className="errors">
          {errors.map((error, i) => (
            <div key={i} className="error">{error}</div>
          ))}
        </div>
      )}

      {transcriptSummary && (
        <div className="summary-section">
          <h3>Conversation Summary</h3>
          <p>{transcriptSummary}</p>
        </div>
      )}

      {fhirSummary && (
        <div className="summary-section">
          <h3>Clinical Analysis</h3>
          <p>{fhirSummary}</p>
        </div>
      )}
    </div>
  );
};
```

---

## Transcript Summarization Endpoint

### cURL

```bash
curl -X POST "https://api.example.com/care-capture/transcript-summarization" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "appointment_id": "123e4567-e89b-12d3-a456-426614174000",
    "user_id": "223e4567-e89b-12d3-a456-426614174000",
    "transcripts": [
      {
        "text": "Patient presents with persistent headache...",
        "created_at": "2024-01-15T10:00:00Z",
        "language_code": "en"
      }
    ]
  }'
```

### Python

```python
def transcript_summarization(
    api: CareCaptureAPI,
    appointment_id: str,
    user_id: str,
    transcripts: List[dict]
):
    payload = {
        "appointment_id": appointment_id,
        "user_id": user_id,
        "transcripts": transcripts
    }
    
    response = requests.post(
        f"{api.base_url}/care-capture/transcript-summarization",
        json=payload,
        headers=api.headers
    )
    response.raise_for_status()
    return response.json()

# Usage
summary = transcript_summarization(
    api=api,
    appointment_id="123e4567-e89b-12d3-a456-426614174000",
    user_id="223e4567-e89b-12d3-a456-426614174000",
    transcripts=[
        {
            "text": "Patient presents with persistent headache for 3 days...",
            "created_at": "2024-01-15T10:00:00Z",
            "language_code": "en"
        }
    ]
)

print(f"Summary: {summary['summary_text']}")
print(f"Metadata: {summary['metadata']}")
```

### JavaScript

```javascript
async function transcriptSummarization(
  api,
  appointmentId,
  userId,
  transcripts
) {
  const response = await fetch(
    `${api.baseUrl}/care-capture/transcript-summarization`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${api.apiToken}`
      },
      body: JSON.stringify({
        appointment_id: appointmentId,
        user_id: userId,
        transcripts
      })
    }
  );

  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
  }

  return response.json();
}

// Usage
const summary = await transcriptSummarization(
  api,
  '123e4567-e89b-12d3-a456-426614174000',
  '223e4567-e89b-12d3-a456-426614174000',
  [
    {
      text: 'Patient presents with persistent headache for 3 days...',
      created_at: '2024-01-15T10:00:00Z',
      language_code: 'en'
    }
  ]
);

console.log(`Summary: ${summary.summary_text}`);
console.log(`Metadata:`, summary.metadata);
```

---

## FHIR Analysis Endpoint

### cURL

```bash
curl -X POST "https://api.example.com/care-capture/fhir-analysis" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "appointment_id": "123e4567-e89b-12d3-a456-426614174000",
    "user_id": "223e4567-e89b-12d3-a456-426614174000",
    "resource_types": ["Condition", "Observation", "MedicationRequest"],
    "analysis_focus": "chronic_conditions"
  }'
```

### Python

```python
def fhir_analysis(
    api: CareCaptureAPI,
    appointment_id: str,
    user_id: str,
    resource_types: List[str] = None,
    analysis_focus: str = None
):
    payload = {
        "appointment_id": appointment_id,
        "user_id": user_id
    }
    
    if resource_types:
        payload["resource_types"] = resource_types
    if analysis_focus:
        payload["analysis_focus"] = analysis_focus
    
    response = requests.post(
        f"{api.base_url}/care-capture/fhir-analysis",
        json=payload,
        headers=api.headers
    )
    response.raise_for_status()
    return response.json()

# Usage
analysis = fhir_analysis(
    api=api,
    appointment_id="123e4567-e89b-12d3-a456-426614174000",
    user_id="223e4567-e89b-12d3-a456-426614174000",
    resource_types=["Condition", "Observation", "MedicationRequest"],
    analysis_focus="chronic_conditions"
)

print(f"Analysis: {analysis['summary_text']}")
print(f"Total resources: {analysis['metadata']['total_resources']}")
print(f"Resource counts: {analysis['metadata']['resource_counts']}")
```

---

## Querying Summaries (NodeAPI)

### cURL

```bash
# Get all summaries for an appointment
curl -X GET "https://api.example.com/conversation-summaries/appointment/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Python

```python
import requests

def get_summaries_by_appointment(
    api: CareCaptureAPI,
    appointment_id: str
):
    """Get all summaries for an appointment (NodeAPI)."""
    response = requests.get(
        f"{api.base_url}/conversation-summaries/appointment/{appointment_id}",
        headers=api.headers
    )
    response.raise_for_status()
    return response.json()

# Usage
summaries = get_summaries_by_appointment(
    api=api,
    appointment_id="123e4567-e89b-12d3-a456-426614174000"
)

# Filter by source
transcript_summary = next(
    (s for s in summaries if s.get('metadata', {}).get('source') == 'transcript'),
    None
)
fhir_summary = next(
    (s for s in summaries if s.get('metadata', {}).get('source') == 'fhir_analysis'),
    None
)

print(f"Found {len(summaries)} summaries")
if transcript_summary:
    print(f"Transcript: {transcript_summary['summary_text'][:100]}...")
if fhir_summary:
    print(f"FHIR: {fhir_summary['summary_text'][:100]}...")
```

### JavaScript

```javascript
async function getSummariesByAppointment(api, appointmentId) {
  const response = await fetch(
    `${api.baseUrl}/conversation-summaries/appointment/${appointmentId}`,
    {
      headers: {
        'Authorization': `Bearer ${api.apiToken}`
      }
    }
  );

  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
  }

  return response.json();
}

// Usage
const summaries = await getSummariesByAppointment(
  api,
  '123e4567-e89b-12d3-a456-426614174000'
);

// Filter by source
const transcriptSummary = summaries.find(
  s => s.metadata?.source === 'transcript'
);
const fhirSummary = summaries.find(
  s => s.metadata?.source === 'fhir_analysis'
);

console.log(`Found ${summaries.length} summaries`);
if (transcriptSummary) {
  console.log('Transcript:', transcriptSummary.summary_text.substring(0, 100) + '...');
}
if (fhirSummary) {
  console.log('FHIR:', fhirSummary.summary_text.substring(0, 100) + '...');
}
```

---

## Error Handling

### Python with Comprehensive Error Handling

```python
from typing import Optional
import logging

logger = logging.getLogger(__name__)

def comprehensive_summarization_with_error_handling(
    api: CareCaptureAPI,
    appointment_id: str,
    user_id: str,
    transcripts: Optional[List[dict]] = None,
    include_fhir_analysis: bool = False
):
    """Execute comprehensive summarization with detailed error handling."""
    try:
        result = api.comprehensive_summarization(
            appointment_id=appointment_id,
            user_id=user_id,
            transcripts=transcripts,
            include_fhir_analysis=include_fhir_analysis
        )
        
        # Check for complete success
        if result['metrics']['error_count'] == 0:
            logger.info(f"Complete success for appointment {appointment_id}")
            return {
                'status': 'success',
                'summaries': result['summaries'],
                'execution_time': result['metrics']['execution_time_seconds']
            }
        
        # Check for partial success
        elif result['metrics']['partial_success']:
            logger.warning(
                f"Partial success for appointment {appointment_id}: "
                f"{result['metrics']['success_count']} succeeded, "
                f"{result['metrics']['error_count']} failed"
            )
            return {
                'status': 'partial_success',
                'summaries': result['summaries'],
                'errors': result['errors'],
                'execution_time': result['metrics']['execution_time_seconds']
            }
        
        # Complete failure
        else:
            logger.error(f"Complete failure for appointment {appointment_id}")
            return {
                'status': 'failure',
                'errors': result['errors']
            }
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout for appointment {appointment_id}")
        return {
            'status': 'error',
            'error_type': 'timeout',
            'error_message': 'Request timed out'
        }
    
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error for appointment {appointment_id}: {e}")
        return {
            'status': 'error',
            'error_type': 'http_error',
            'error_message': str(e),
            'status_code': e.response.status_code if e.response else None
        }
    
    except Exception as e:
        logger.exception(f"Unexpected error for appointment {appointment_id}")
        return {
            'status': 'error',
            'error_type': 'unexpected',
            'error_message': str(e)
        }

# Usage
result = comprehensive_summarization_with_error_handling(
    api=api,
    appointment_id="123e4567-e89b-12d3-a456-426614174000",
    user_id="223e4567-e89b-12d3-a456-426614174000",
    transcripts=[{"text": "Patient presents..."}],
    include_fhir_analysis=True
)

if result['status'] == 'success':
    print("All operations succeeded!")
    for summary in result['summaries']:
        print(f"- {summary['metadata']['source']}: {summary['summary_text'][:50]}...")
elif result['status'] == 'partial_success':
    print("Some operations succeeded:")
    for summary in result['summaries']:
        print(f"- {summary['metadata']['source']}: ✓")
    print("Some operations failed:")
    for error in result['errors']:
        print(f"- {error['source']}: {error['error_message']}")
else:
    print(f"Operation failed: {result.get('error_message', 'Unknown error')}")
```

### TypeScript with Error Handling

```typescript
interface OperationResult {
  status: 'success' | 'partial_success' | 'failure' | 'error';
  summaries?: any[];
  errors?: any[];
  execution_time?: number;
  error_type?: string;
  error_message?: string;
}

async function comprehensiveSummarizationWithErrorHandling(
  api: CareCaptureAPI,
  appointmentId: string,
  userId: string,
  transcripts?: Transcript[],
  includeFhirAnalysis: boolean = false
): Promise<OperationResult> {
  try {
    const result = await api.comprehensiveSummarization({
      appointment_id: appointmentId,
      user_id: userId,
      transcripts,
      include_fhir_analysis: includeFhirAnalysis
    });

    // Complete success
    if (result.metrics.error_count === 0) {
      console.log(`Complete success for appointment ${appointmentId}`);
      return {
        status: 'success',
        summaries: result.summaries,
        execution_time: result.metrics.execution_time_seconds
      };
    }

    // Partial success
    if (result.metrics.partial_success) {
      console.warn(
        `Partial success for appointment ${appointmentId}: ` +
        `${result.metrics.success_count} succeeded, ` +
        `${result.metrics.error_count} failed`
      );
      return {
        status: 'partial_success',
        summaries: result.summaries,
        errors: result.errors,
        execution_time: result.metrics.execution_time_seconds
      };
    }

    // Complete failure
    console.error(`Complete failure for appointment ${appointmentId}`);
    return {
      status: 'failure',
      errors: result.errors
    };

  } catch (error) {
    console.error(`Error for appointment ${appointmentId}:`, error);
    
    if (error instanceof TypeError && error.message.includes('timeout')) {
      return {
        status: 'error',
        error_type: 'timeout',
        error_message: 'Request timed out'
      };
    }

    return {
      status: 'error',
      error_type: 'unexpected',
      error_message: error.message || 'Unknown error'
    };
  }
}

// Usage
const result = await comprehensiveSummarizationWithErrorHandling(
  api,
  '123e4567-e89b-12d3-a456-426614174000',
  '223e4567-e89b-12d3-a456-426614174000',
  [{ text: 'Patient presents...' }],
  true
);

switch (result.status) {
  case 'success':
    console.log('All operations succeeded!');
    result.summaries?.forEach(summary => {
      console.log(`- ${summary.metadata.source}: ${summary.summary_text.substring(0, 50)}...`);
    });
    break;

  case 'partial_success':
    console.log('Some operations succeeded:');
    result.summaries?.forEach(summary => {
      console.log(`- ${summary.metadata.source}: ✓`);
    });
    console.log('Some operations failed:');
    result.errors?.forEach(error => {
      console.log(`- ${error.source}: ${error.error_message}`);
    });
    break;

  case 'failure':
  case 'error':
    console.error(`Operation failed: ${result.error_message || 'Unknown error'}`);
    break;
}
```

---

## Advanced Usage

### Retry Logic with Exponential Backoff

```python
import time
from typing import Optional

def comprehensive_summarization_with_retry(
    api: CareCaptureAPI,
    appointment_id: str,
    user_id: str,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    **kwargs
):
    """Execute with exponential backoff retry."""
    delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            result = api.comprehensive_summarization(
                appointment_id=appointment_id,
                user_id=user_id,
                **kwargs
            )
            
            # Success or partial success - don't retry
            if result['metrics']['success_count'] > 0:
                return result
            
            # Complete failure with no timeout - retry
            if not result['metrics']['timeout_occurred']:
                logger.warning(f"Attempt {attempt + 1} failed, retrying...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
                continue
            
            # Timeout - don't retry
            return result
            
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            logger.warning(f"Attempt {attempt + 1} failed with {e}, retrying...")
            time.sleep(delay)
            delay *= 2
    
    raise Exception(f"Failed after {max_retries} attempts")

# Usage
result = comprehensive_summarization_with_retry(
    api=api,
    appointment_id="123e4567-e89b-12d3-a456-426614174000",
    user_id="223e4567-e89b-12d3-a456-426614174000",
    transcripts=[{"text": "..."}],
    include_fhir_analysis=True,
    max_retries=3
)
```

### Batch Processing Multiple Appointments

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def process_appointments_batch(
    api: CareCaptureAPI,
    appointments: List[dict],
    max_concurrent: int = 5
):
    """Process multiple appointments concurrently."""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_one(appointment):
        async with semaphore:
            try:
                result = await asyncio.to_thread(
                    api.comprehensive_summarization,
                    appointment_id=appointment['appointment_id'],
                    user_id=appointment['user_id'],
                    transcripts=appointment.get('transcripts'),
                    include_fhir_analysis=appointment.get('include_fhir_analysis', False)
                )
                return {
                    'appointment_id': appointment['appointment_id'],
                    'status': 'success',
                    'result': result
                }
            except Exception as e:
                return {
                    'appointment_id': appointment['appointment_id'],
                    'status': 'error',
                    'error': str(e)
                }
    
    tasks = [process_one(apt) for apt in appointments]
    results = await asyncio.gather(*tasks)
    
    return results

# Usage
appointments = [
    {
        'appointment_id': '123e4567...',
        'user_id': '223e4567...',
        'transcripts': [{'text': '...'}],
        'include_fhir_analysis': True
    },
    # ... more appointments
]

results = asyncio.run(
    process_appointments_batch(api, appointments, max_concurrent=5)
)

# Analyze results
successful = [r for r in results if r['status'] == 'success']
failed = [r for r in results if r['status'] == 'error']

print(f"Processed {len(successful)} successfully, {len(failed)} failed")
```

---

## Related Documentation

- [Comprehensive Summarization](./COMPREHENSIVE_SUMMARIZATION.md) - Endpoint details
- [Architecture](./ARCHITECTURE.md) - Service layer design
- [Metadata Implementation](./METADATA_IMPLEMENTATION.md) - Metadata usage
- [Breaking Changes Analysis](./BREAKING_CHANGES_ANALYSIS.md) - Compatibility info

---

## Support

For questions or issues:
- Check [API Documentation](../README.md)
- Review [Troubleshooting Guide](./COMPREHENSIVE_SUMMARIZATION.md#troubleshooting)
- Contact engineering team
