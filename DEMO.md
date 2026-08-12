# Demo — Aria voice

```bash
git clone https://github.com/Maan-14/voice-ai-appliance-diagnostic-agent.git
cd voice-ai-appliance-diagnostic-agent
git checkout demo

cp .env.example .env   # fill required values
brew install portaudio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p data uploads

export SSL_CERT_FILE=$(python -c "import certifi; print(certifi.where())")
python -m scripts.seed
python -m scripts.mic_voice
```

Allow Microphone when asked. Wear headphones. Speak after Aria greets you. `Ctrl+C` to stop.
