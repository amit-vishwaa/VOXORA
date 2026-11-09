"""Placeholders for REAL providers. They are NOT implemented: they exist so the registry,
admin UI and docs show where real integrations plug in. Each raises NotConfigured when used."""
import os

from .base import NotConfigured, STTProvider, LLMProvider, TTSProvider, TelephonyProvider


def _need(env):
    if not os.environ.get(env):
        raise NotConfigured(f"{env} is not set and this adapter is a stub (not implemented yet)")
    raise NotConfigured("Adapter is a stub: implement the API call in this class (see CONTINUE_WITH_AI.md)")


class DeepgramSTT(STTProvider):
    simulated, implemented, note = False, False, "Stub. Needs DEEPGRAM_API_KEY + implementation."

    def transcribe(self, audio, language, ctx):
        _need("DEEPGRAM_API_KEY")


class OpenAILLM(LLMProvider):
    simulated, implemented, note = False, False, "Stub. Needs OPENAI_API_KEY + implementation."

    def respond(self, ctx):
        _need("OPENAI_API_KEY")

    def summarize(self, ctx):
        _need("OPENAI_API_KEY")


class ElevenLabsTTS(TTSProvider):
    simulated, implemented, note = False, False, "Stub. Needs ELEVENLABS_API_KEY + implementation."

    def synthesize(self, text, language, voice, ctx):
        _need("ELEVENLABS_API_KEY")


class TwilioTelephony(TelephonyProvider):
    simulated, implemented, note = False, False, "Stub. Needs TWILIO_ACCOUNT_SID/AUTH_TOKEN + implementation."

    def place_call(self, from_number, to_number, direction, ctx):
        _need("TWILIO_AUTH_TOKEN")

    def transfer(self, sid, target):
        _need("TWILIO_AUTH_TOKEN")
