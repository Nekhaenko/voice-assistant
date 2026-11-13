# Voice Interview Assistant

A desktop assistant that listens to your interview conversation in real-time,
transcribes English speech, translates it to Russian, and displays the result
in a non-intrusive translucent overlay window.

Designed for job candidates who need language support during interviews without
distracting from the conversation.

## Architecture

```
System Audio ──► sounddevice ──► VAD ──► Vosk (ASR) ──► Google Translate ──► CustomTkinter Overlay
```

| Component          | Library           | Purpose                          |
|--------------------|-------------------|----------------------------------|
| Audio Capture      | `sounddevice`     | Records system audio via PortAudio |
| Voice Detection    | `webrtcvad`       | Skips silence segments           |
| Speech-to-Text     | `vosk`            | Offline English transcription    |
| Translation        | `deep-translator` | English → Russian (Google)       |
| Display            | `customtkinter`   | Draggable translucent overlay    |

## Prerequisites

### 1. Python 3.10+

The project requires Python ≥ 3.10. Verify with:

```bash
python3 --version
```

### 2. Virtual Audio Driver (macOS)

To capture system audio (what plays through your speakers), you need a loopback driver:

**BlackHole (recommended, free):**

```bash
# Download from https://blackhole.audio/
# Or via Homebrew Cask:
brew install --cask blackhole-2ch
```

After installing BlackHole:
1. Open **Audio MIDI Setup** (`/Applications/Utilities/Audio MIDI Setup.app`)
2. Click **+** → **Create Multi-Output Device**
3. Add both your speakers and **BlackHole 2ch**
4. In Voice Assist settings, select **BlackHole 2ch** as the audio source

**Alternative: SoundFlower** (older, less maintained)
- Download from https://soundflower.en.softonic.com/mac

### 3. Virtual Audio Driver (Windows)

**VB-Audio Virtual Cable (free):**

```bash
# Download and install from https://www.vb-audio.com/Cable/
```

After installation, select **Cable Input** as the audio source in the app.

### 4. Virtual Audio Driver (Linux)

PulseAudio/PipeWire typically supports loopback natively:

```bash
# PulseAudio
pactl load-module module-null-sink sink_name=loopback

# PipeWire (usually works out of the box via wireplumber)
```

Select the loopback sink in the app settings.

## Installation

### Sber Corporate Environment (internal PyPI)

This project is configured for the Sber internal package mirror:

```bash
# Install uv (fast Python package manager) if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env  # or restart your shell

cd voice-assistent
uv pip install -e . \
  --index-url "https://token:<your-token>@sberosc.sigma.sbrf.ru/repo/pypi/simple"
```

Replace `<your-token>` with your Nexus authentication token.

### Standard pip (external PyPI)

If installing from PyPI.org directly:

```bash
pip install -e .
```

### Manual dependency install

If any dependency fails, install them individually:

```bash
pip install sounddevice vosk deep-translator customtkinter webrtcvad soundfile psutil
```

## Usage

### Starting the app

```bash
cd voice-assistent
python3 -m voice_assist.main
```

Or install the console script:

```bash
uv pip install -e . --index-url "..."
voice-assist
```

### Controls

Once the app launches, a small floating panel appears:

| Button        | Action                                      |
|---------------|---------------------------------------------|
| ▶ / ■         | Start/Stop audio capture                    |
| ⚙            | Open Settings dialog                        |
| ─            | Minimize overlay window                     |

The overlay window shows:
```
Could you describe a challenging project you worked on?
  Опишите сложный проект, над которым вы работали?

Tell me about a time you resolved a conflict in your team.
  Расскажите о случае, когда вы разрешили конфликт в команде.
```

### Settings

The Settings dialog offers:

- **Audio Source:** Select which input device to capture from
- **Bilingual:** Toggle whether to show original English text
- **Overlay Opacity:** Slider from fully transparent to solid
- **Show Timestamps:** Add `[HH:MM:SS]` prefixes to each entry
- **Toggle Hotkey:** Configure keyboard shortcut to show/hide overlay

### Exporting Transcript

A session transcript can be exported from within the application. This saves all
English→Russian pairs to a `.txt` or `.json` file in the current directory.

## Troubleshooting

### "No audio devices found"

Your virtual audio driver may not be installed or not selected as the default input.
Check Audio MIDI Setup (macOS) or Sound settings (Windows/Linux).

### "Failed to open audio stream"

The selected device might be in use by another application. Try a different device,
or ensure no other app is capturing from the same source.

### No translation appearing

- Check internet connectivity (Google Translate requires network access)
- Check the console logs for errors: run with `PYTHONVERBOSE=1 python3 -m voice_assist.main`
- The overlay auto-hides after 15 seconds of no new content; wait for the interviewer to speak

### Translation quality is poor

Google Translate handles general conversation well but may struggle with highly technical jargon.
Consider supplementing with a personal glossary or using voice-assist's session export to review
after the interview.

### High CPU usage

Vosk's small model uses minimal CPU (~5-15%). If usage is higher:
- Close other applications
- Reduce the overlay font size (edit `overlay/window.py`, `_FONT_SIZE_RU`)
- Try a lower VAD aggressiveness mode in `audio/vad.py` (`mode=0`)

## Project Structure

```
voice_assist/
├── main.py               # Entry point & pipeline wiring
├── audio/
│   ├── capture.py        # Audio device enumeration & stream management
│   └── vad.py            # WebRTC VAD wrapper with hysteresis smoothing
├── speech/
│   ├── whisper_engine.py # Vosk-based transcription engine
│   └── buffer.py         # Sliding window buffer with VAD-driven flushing
├── translator/
│   └── engine.py         # Google Translate wrapper with offline fallback
├── overlay/
│   └── window.py         # CustomTkinter translucent topmost window
├── memory/
│   └── session.py        # Session-scoped translation memory + export
├── config/
│   └── settings.py       # Persistent JSON configuration
└── ui/
    └── tray.py           # Floating controls panel & settings dialog
```

## License

Proprietary — internal use only.
