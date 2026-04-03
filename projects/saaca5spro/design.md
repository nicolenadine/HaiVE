# SAACA5SPRO

## Product overview

**Product story:**<br>
V0      → V1         → V2    → V3     → V∞<br>
Capture → Understand → Query → Assist → Co-create

&nbsp;&nbsp;**V0:** Capture - offline unstructured transcription, pdf parsing<br>
&nbsp;&nbsp;**V1:** Understand - structured transcript & pdf parsing, search, generated summaries<br>
&nbsp;&nbsp;**V2:** Query - rulebook explainer, transcription entity extraction, narrative generation, UI<br>
&nbsp;&nbsp;**V3:** Assist - real-time GM copilot<br>
&nbsp;&nbsp;**V∞:** Co-Create - content engine and platform


| Version | Usage (Capabilities) | Functional Requirements | Non-Functional Requirements |
|--------|----------------------|--------------------------|-----------------------------|
| **V0 (MVP)** | - Ask questions of demo game books<br>- Speech-to-text demo<br>- Simple LLM query engine with adjustable context | - Single user<br>&nbsp;&nbsp;- No session history<br>&nbsp;&nbsp;- No authentication<br>- Unformatted transcript output<br>- Pre-loaded game books only<br>- Simple CLI | - Offline transcription<br>- Offline speaker separation<br>- Offline rulebook parsing<br>- Component skeleton suitable for future versions<br>- MCP for PDF queries<br>- Vector DB demo for game book storage? |
| **V1 (Internal Use)** | **V0 plus…**<br>- Query game books<br>- Generate tagged game transcripts<br>- Generate session summaries | **V0 plus…**<br>- Multi-user support<br>&nbsp;&nbsp;- Session memory<br>&nbsp;&nbsp;- Authentication<br>- Structured transcripts<br>- Easy transcript viewing<br>- Session summaries | **V0 plus…**<br>- Prompt orchestration and pipelines<br>- File system access<br>&nbsp;- Transcript storage<br>&nbsp;- Summary storage<br>- Vector database for embeddings<br>- Data lakes for rulebook PDFs, transcript audio<br>- Schema for transcript and sessions<br>- Human-assisted ingestion pipeline for rulebooks (parsing PDFs, chunking, embedding)<br>- Guaranteed responses (retries, fallback)<br>- Basic observability (logs, metrics)<br>- Event-driven architecture<br>- Critic loop proof of concept |
| **V2 (Friends & Family)** | **V1 plus…**<br>- Generate narrative (“novel-style”) summaries<br>- Generate board game rule book explainer <br>- Query PC & NPC details<br>- Query PC inventory<br>- Query past session summaries<br>- Generate / retrieve NPC & world images | **V1 plus…**<br>- REST API<br>- Simple GUI<br>- Transcript editing (view, edit, annotate, share)<br>- Auto-annotated transcripts | **V1 plus…**<br>- UI permissions<br>- basic UX state management<br>- Scalability for multiple concurrent users<br>- Moderate latency (interactive UX)<br>- Basic reliability (session persistence, backups, reconnect)<br>- Image generation and storage pipeline |
| **V3 (Friends of Friends)** | **V2 plus…**<br>- Auto-generate and deliver GM content based on latest session data | **V2 plus…**<br>- Advanced GUI<br>- “Book mode” for reading summaries<br>- Live transcript streaming<br>- Live suggestions during gameplay<br>- Dynamic game book management (add/remove) | **V2 plus…**<br>- Real-time responsiveness<br>- Higher availability (multi-session support)<br>- Streaming infra (websocket, gRPC)<br>- Improved observability (LGTM, W&B) <br>-Low-latency inference strategy<br>&nbsp;&nbsp;- Caching<br>&nbsp;&nbsp;- Partial updates<br>- Mobile support |
| **V∞ (Vision)** | - AI-generated podcast with voice-over of campaigns<br>- AI-generated podcast style or visual explainer for any game manual<br>- AI-generated printable (raw) or purchasable (edited, bound) campaign books<br>- Universal rule explainer for any system<br>- Always-on real-time assistant (visuals, rulings, NPC dialogue)<br>- Integration with advanced AI providers (“bring your own model/API key”)<br>&nbsp;&nbsp;- Abstraction layer over model provider | - Extensible plugin ecosystem<br>- Cross-platform clients (web, mobile, desktop)<br>- Marketplace for content / modules | - High scalability (cloud-native)<br>- Cost-efficient inference orchestration<br>- Strong data privacy & access controls<br>- Near real-time latency for interactive features |

## V0 System Overview (capture only)

```
            -> transcription       v 
audio input |                      |--> parsed audio output
            -> speaker Separation  ^ 
```

- Fully offline
- Swappable services
- Event-driven via NATS
- Minimal persistence
- Docker compose orchestration

### Core technologies

- **Orchestration:** Docker compose (quick setup, sandboxed from the start)
- **Model delivery:** Ollama (easy interface, fast startup)
- **Microservie communication:** NATS (event driven, low overhead, and good for edge computing)

## Microservices

### Event bus
**Purpose:**<br>
Communication layer to decouple services 

**Responsibilities:**<br>

**Tech:**<br>
[NATS](https://nats.io/)

### Audio capture

**Purpose:**<br>
Capture microphone input and stream audio chunks
- record from system mic
- chunk audio into frames
- publish audio events

**Responsibilities:**<br>

**Tech:**<br>
[python-sounddevice](https://github.com/spatialaudio/python-sounddevice)

**NATS:**<br>
_Publish_
```bash
subject: audio.raw
payload: { session_id, chunk_id, bytes }
```

### Audio tagging

**Purpose:**<br>
arse audio to extract speakers

**Responsibilities:**<br>

**Tech:**<br>
[Pyannote](https://github.com/pyannote/pyannote-audio)

**NATS:**<br>
_Subscribe_<br>
`audio.raw`<br>
_Publish_<br>
```bash
subject: speakers.json
payload: { session_id, chunk_id, speakers }
```

### Transcription

**Purpose:**<br>
Convert audio → text (offline)
- Consume audio chunks
- Run speech-to-text
- Emit transcript segmens

**Responsibilities:**<br>

**Tech:**<br>
[faster whisper](https://github.com/SYSTRAN/faster-whisper)?

**NATS:**<br>
_Subscribe_<br>
`audio.raw`<br>
_Publish_<br>
```bash
subject: transcript.raw
payload: { session_id, chunk_id, text, timestamps }
```

### Structured transcription

**Purpose:**<br>
Transform transcription into a structured document.

**Responsibilities:**<br>

**Tech:**<br>
expert system with LLM polish

**NATS:**<br>
_Subscribe_<br>
`transcript.raw`<br>
`speakers.json`<br>
_Publish_<br>
```bash
subject: transcript.labeled
payload: { session_id, chunk_id, speaker_id, text }
```

### Game book loader

**Purpose:**<br>
Provide preloaded static content

**Responsibilities:**<br>
- Expose raw text for three rulebooks

**Tech:**<br>
- Simlpe file loader (PDF -> text)

**API:**<br>
Request/response framework


### CLI interface service

**Purpose:**<br>
User-facing inerface

**Responsibilities:**<br>
- start/stop streaming service

**Tech:**<br>
[argparse](https://realpython.com/command-line-interfaces-python-argparse/) -- CLI support
[rich](https://github.com/textualize/rich) -- auto colorize transcript output

**NATS:**<br>
_Publish_<br>
```bash
subject: control.commands
payload: { action: start|stop }
```
