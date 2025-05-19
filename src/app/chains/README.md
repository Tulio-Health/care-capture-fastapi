# Chains Directory Documentation

This directory contains various LangChain-based implementations for different features of the application. Each chain is designed to handle specific tasks using LLM (Large Language Model) capabilities.

## Core Features

### 1. Medical Chat Chain (`chat.py`)
- Implements a conversational medical assistant
- Features:
  - Context-aware responses based on patient profile and visit history
  - Professional medical communication
  - Clear explanation of medical terms
  - Integration with chat history
  - Uses GPT-4 model with temperature 0.2 for consistent responses

### 2. Schedule Visit Chain (`schedule_visit/`)
- Handles medical appointment scheduling
- Features:
  - Intelligent doctor matching based on:
    - Explicit doctor name mentions
    - Specialty requirements
    - Location preferences
    - Availability
  - Supports fuzzy name matching
  - Handles date scheduling with current date context
  - Returns structured appointment data

### 3. Transcript Summarization Chain (`transcript_summarization/`)
- Processes and summarizes medical conversations
- Features:
  - Extracts key medical information
  - Maintains medical terminology accuracy
  - Structured output format
  - Handles:
    - Medications
    - Diagnoses
    - Medical instructions
    - Recommendations
  - Includes LangSmith tracing for monitoring

### 4. AI Chat Intents (`ai-chat-intents/`)
Contains specialized intent handlers for different types of medical queries:

#### a. Health Insights Intent
- Processes health-related queries
- Provides insights based on patient data

#### b. Past Visit Intent
- Handles queries about previous medical visits
- Retrieves and summarizes past visit information

#### c. Medical Inquiry Intent
- Processes general medical questions
- Provides appropriate medical information

#### d. Intent Identifier
- Classifies user queries into appropriate categories
- Routes queries to relevant handlers

## Technical Details

- All chains use the GPT-4 model with temperature 0.2 for consistent outputs
- Implemented using LangChain framework
- Includes proper error handling and output parsing
- Uses Pydantic models for structured data handling
- Integrates with Redis for chat history management

## Usage

Each chain can be instantiated and used independently. Example:

```python
# For medical chat
chat_chain = MedicalChatChain()
response = chat_chain.chat(input_text, context)

# For appointment scheduling
schedule_chain = ScheduleVisitChain()
appointment = schedule_chain.schedule_visit(text=request_text, providers=available_providers)

# For transcript summarization
summarizer = TranscriptSummarizationChain()
summary = summarizer.summarize(conversation_text)
```

## Dependencies

- LangChain
- OpenAI GPT-4
- Redis (for chat history)
- Pydantic (for data validation)
- LangSmith (for tracing)
