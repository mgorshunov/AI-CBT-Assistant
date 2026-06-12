# AI-CBT-Assistant
# Overview

AI-Powered CBT Assistant is a conversational AI application built to explore long-form, user-centric interactions through a Telegram interface. The system combines large language models (LLMs), persistent conversation memory, automatic context summarization, speech-to-text transcription, and user session management to support coherent multi-session conversations.

The project was designed to investigate practical challenges encountered when deploying conversational AI systems in real-world settings, including memory management, context-window limitations, user persistence, conversational continuity, and interaction quality over time.

While the application uses cognitive behavioral therapy (CBT)-inspired conversational techniques, the primary focus of the project is the design and implementation of production-oriented conversational AI workflows.

# Architecture

User → Telegram Bot → Application Layer → LLM API → Response Generation

Core Components:

• Telegram interface for text and voice interactions

• Conversation management layer for maintaining user history across sessions

• PostgreSQL database for persistent storage of conversation records and usage metrics

• Context summarization module for compressing long conversations when token limits are reached

• Speech-to-text pipeline for voice message transcription

• LLM inference layer for response generation

• Rate limiting and operational controls to manage system usage

The system stores user interactions, maintains conversational state, and automatically summarizes prior exchanges when conversation history exceeds predefined thresholds.

# Evaluation

- Tested conversation coherence across long interactions
- Evaluated summarization quality after context compression
- Monitored transcription accuracy for voice inputs
- Iteratively refined prompts to improve response consistency

# Features

### Conversational AI

* Natural language conversations through Telegram
* Multi-session conversation continuity
* Context-aware responses using historical interactions

### Memory Management

* Persistent conversation storage
* Automatic conversation retrieval
* Conversation history compression through LLM-based summarization

### Voice Support

* Voice message upload
* Speech-to-text transcription
* Seamless integration of voice and text interactions

### User Management

* Session persistence
* Usage tracking
* Message counting
* Rate limiting to prevent abuse

### Operational Features

* Error handling and logging
* Database-backed persistence
* Conversation reset functionality
* API key rotation support

# Technical Stack

Backend:

* Python
* SQLAlchemy
* PostgreSQL

AI & NLP:

* Llama 3 (via Groq API)
* Whisper Large V3
* Prompt Engineering
* Conversation Summarization

Application Layer:

* Telegram Bot API
* Async Event Handling

Infrastructure:

* Environment Variable Management
* Logging & Monitoring
* Database Persistence
* API Integrations

# Lessons Learned

### Conversation Memory Is Hard

Maintaining coherent long-form conversations requires more than storing chat history. As conversations grow, context-window constraints force tradeoffs between retaining detail and preserving responsiveness.

### Summarization Becomes a Core System Component

Conversation summarization proved essential for maintaining continuity while controlling token usage. Effective summaries preserve context while minimizing information loss.

### User Behavior Is Unpredictable

Users frequently switch topics, provide incomplete information, or revisit prior discussions. Robust conversational systems must handle these transitions gracefully.

### Voice Interactions Introduce New Failure Modes

Speech recognition errors, audio quality issues, and transcription variability significantly influence downstream response quality.

### Prompt Design Requires Continuous Iteration

Small prompt changes can substantially alter response quality, conversational tone, and consistency. Prompt engineering became an iterative evaluation process rather than a one-time task.

### Real-World AI Systems Require More Than LLMs

Reliable conversational experiences depend heavily on memory management, persistence, workflow orchestration, monitoring, and operational safeguards in addition to the underlying model.

# Disclaimer
This project is intended for research, educational, and software development purposes only. It is not a medical device, mental health service, or substitute for professional medical or psychological care.
The research, views, and opinions expressed on this website are strictly my own. They do not necessarily reflect the official policy, position, or regulatory perspectives of my current or previous employers.

