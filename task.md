# Voice AI: Home Appliance Diagnostic Agent  
## Sears Home Services — AI Engineering Take-Home Project

---

# 1. Objective

Build an **end-to-end Voice AI system** that handles inbound calls from customers experiencing appliance issues.

The system must:

- Accept inbound calls
- Diagnose appliance issues through conversation
- Provide troubleshooting steps
- Schedule technician visits when needed
- Optionally support visual diagnosis via image upload

---

# 2. Core Scenario

A homeowner calls because an appliance is malfunctioning.

The Voice Agent must:

1. Greet caller professionally
2. Identify appliance type
3. Understand symptoms
4. Ask diagnostic questions
5. Provide troubleshooting steps
6. Schedule technician if issue unresolved
7. Optionally request image upload

---

# 3. Functional Requirements

## Tier 1 — Core Voice Functionality (MANDATORY)

### 3.1 Inbound Call Handling

System must:

- Accept inbound phone calls
- Engage in natural voice conversation
- Maintain conversational flow

---

### 3.2 Appliance Identification

Identify appliance type from conversation.

Supported examples:

- Washer
- Dryer
- Refrigerator
- Dishwasher
- Oven
- HVAC
- Others

---

### 3.3 Symptom Collection

Collect:

- Problem description
- Start time of issue
- Error codes
- Sounds
- Observed behavior

---

### 3.4 Diagnostic Guidance

System should:

- Provide relevant troubleshooting steps
- Adapt questions based on responses
- Guide caller step-by-step

---

### 3.5 Conversation Memory

System must:

- Maintain call context
- Avoid repeating questions
- Persist collected information

---

# Tier 2 — Technician Scheduling (MANDATORY)

## 4. Scheduling System

### 4.1 Database Design

Create database including:

#### Technicians Table

Fields:

- id
- name
- contact info
- specialties
- employment details

---

#### Service Areas Table

Fields:

- technician_id
- zip_code

---

#### Specialties Table

Fields:

- technician_id
- appliance_type

---

#### Availability Table

Fields:

- technician_id
- time_slot
- constraints

---

#### Appointments Table

Fields:

- customer
- technician
- scheduled_time
- appliance_type

---

### 4.2 Sample Data

Populate:

- 5–10 technicians
- Multiple zip codes
- Multiple appliance specialties
- Available time slots

---

### 4.3 Availability Matching Logic

Input:

- Zip code
- Appliance type

Output:

- Matching technicians

---

### 4.4 Scheduling Flow

System must:

1. Ask customer availability
2. Find matching technician slots
3. Offer available times
4. Confirm booking

---

### 4.5 Confirmation

Before ending call:

- Read appointment details aloud
- Confirm date/time
- Confirm technician

---

# Tier 3 — Visual Diagnosis (OPTIONAL)

## 5. Image-Based Diagnosis

### 5.1 Email Capture

If needed:

- Request customer email

---

### 5.2 Upload Link Generation

System must:

- Send email with upload link
- Link must be unique

---

### 5.3 Image Processing

When image uploaded:

- Detect appliance type
- Identify visible issues

Possible tools:

- Vision LLM
- CV models
- API services

---

### 5.4 Enhanced Troubleshooting

Use image insights to:

- Improve diagnosis
- Provide better troubleshooting

---

# 6. Technical Stack (Flexible)

You may choose any tools.

Recommended categories:

---

## Voice / Telephony

Examples:

- Twilio
- Vonage
- Plivo
- Telnyx

---

## Speech-to-Text (STT)

Examples:

- Whisper
- Google STT
- Deepgram
- AssemblyAI

---

## Text-to-Speech (TTS)

Examples:

- ElevenLabs
- OpenAI TTS
- Google TTS
- Amazon Polly

---

## LLM / Agent Framework

Examples:

- GPT-4
- Claude
- LangChain
- LlamaIndex
- Custom agents

---

## Backend

Examples:

- Python (FastAPI, Flask)
- Node.js
- Go

---

## Database

Examples:

- PostgreSQL
- MySQL
- SQLite
- MongoDB

---

## Vision (Optional)

Examples:

- GPT-4 Vision
- Claude Vision
- Google Vision API

---

# 7. Deliverables

You must submit:

---

## 7.1 Source Code

Include:

- Complete Git repository
- All required code

---

## 7.2 Docker Deployment

Must include:

- Docker Compose file
- One-command system startup

Example:

```bash
docker-compose up