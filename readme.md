# COLUM Beta 1

**COLUM** is a production-oriented AI desktop assistant and desktop control system for Windows, inspired by the concept of JARVIS.

## Features

- **Voice & Text Interaction** - Natural language commands via voice or text
- **OpenRouter Integration** - Uses OpenRouter API for LLM inference with dynamic model selection
- **Desktop Control** - Application launching, window management, file operations, keyboard/mouse control
- **Web Automation** - Search, browse, and extract information from the web
- **Structured Tool System** - Safe, permission-based tool execution with validation
- **Memory & Context** - Conversation history, task history, and user preferences
- **Security First** - Risk-based confirmation system, no arbitrary code execution
- **Modern UI** - Clean, professional dashboard with real-time status

## Architecture

```
COLUM/
├── app/                    # Python backend
│   ├── core/               # Event bus, lifecycle, server
│   ├── ai/                 # OpenRouter client, model management
│   ├── voice/              # STT, TTS, wake word
│   ├── tools/              # Desktop control tools
│   ├── automation/         # Task planning & execution
│   ├── memory/             # Conversation & preference storage
│   ├── security/           # Permission & confirmation system
│   ├── config/             # Configuration loader
│   └── utils/              # Logging, helpers
├── frontend/               # HTML/CSS/JS dashboard
├── tests/                  # Test suite
├── scripts/                # Setup & run scripts
├── data/                   # Logs, cache, memory
└── config.yaml             # Main configuration
```

## Quick Start

### Prerequisites

- Windows 10/11
- Python 3.10+
- OpenRouter API key (get one at https://openrouter.ai/keys)

### Installation

```powershell
# Clone or navigate to the project
cd Colum-beta-1

# Run setup script
.\scripts\setup.ps1

# Edit .env and add your OPENROUTER_API_KEY
notepad .env

# Run COLUM
.\scripts\run.ps1
```

### Manual Installation

```powershell
# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Copy environment template
copy .env.example .env
# Edit .env with your API key

# Run
python -m app.main
```

## Configuration

Key settings in `.env`:

```env
# Required
OPENROUTER_API_KEY=your_key_here

# Optional
OPENROUTER_MODE=free              # free, paid, or specific
OPENROUTER_MODEL=                 # Specific model ID when mode=specific
COLUM_WAKE_WORD=COLUM             # Wake word
COLUM_INACTIVITY_TIMEOUT_MINUTES=5
VOICE_STT_PROVIDER=whisper_local  # whisper_local, whisper_api, google, azure, vosk
VOICE_TTS_PROVIDER=edge           # edge, google, azure, coqui, piper
LOG_LEVEL=INFO
```

Or configure via `config.yaml` for more options.

## Usage

1. **Start COLUM** - Runs HTTP server on port 8765, WebSocket on 8766
2. **Open Dashboard** - Navigate to `http://localhost:8765`
3. **Interact** - Type messages or use the microphone button
4. **Voice Activation** - Say "COLUM" to activate (when wake word is implemented)

### Example Commands

- "Open Chrome"
- "Search for Python tutorials on YouTube"
- "Create a file called notes.txt with content 'Hello World'"
- "Take a screenshot"
- "What's the weather in Tokyo?"

## Project Structure

See `PROJECT_STRUCTURE.md` in the Project Plan directory for detailed architecture.

## Development

### Running Tests

```powershell
.\.venv\Scripts\Activate.ps1
pytest tests/ -v
```

### Code Quality

```powershell
# Lint
ruff check app/

# Type check
mypy app/

# Format
ruff format app/
```

## Security

- All tool execution goes through a permission system
- High-risk operations require explicit confirmation
- API keys never logged or exposed
- No arbitrary shell command execution by the LLM

## Roadmap

See `ROADMAP.md` in the Project Plan directory.

### Phase 1 - Foundation ✓
- Project structure
- Configuration system
- Logging
- HTTP/WebSocket server
- Basic dashboard

### Phase 2 - AI Brain (Next)
- OpenRouter client
- Model selection & fallback
- Streaming responses
- Tool calling

### Phase 3 - Tools
- Application control
- File operations
- Window management
- Terminal commands

### Phase 4 - Voice
- Wake word detection
- Speech-to-text
- Text-to-speech

## License

MIT License - See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## Support

- Issues: GitHub Issues
- Documentation: See `docs/` and Project Plan directory