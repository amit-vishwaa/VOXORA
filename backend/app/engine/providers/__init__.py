"""Provider registry. To add a real provider: subclass the interface in base.py and register it here."""
from .base import ProviderError, NotConfigured
from .mock import MockSTT, MockLLM, MockTTS, MockTelephony
from .stubs import DeepgramSTT, OpenAILLM, ElevenLabsTTS, TwilioTelephony

REGISTRY = {
    "stt": {"mock-stt": MockSTT, "deepgram-stt": DeepgramSTT},
    "llm": {"mock-llm": MockLLM, "openai-llm": OpenAILLM},
    "tts": {"mock-tts": MockTTS, "elevenlabs-tts": ElevenLabsTTS},
    "telephony": {"mock-telephony": MockTelephony, "twilio-telephony": TwilioTelephony},
}


def get(kind, name):
    try:
        return REGISTRY[kind][name]()
    except KeyError:
        raise ProviderError(f"Unknown {kind} provider '{name}'")


def exists(kind, name):
    return name in REGISTRY.get(kind, {})


def describe():
    out = []
    for kind, items in REGISTRY.items():
        for name, cls in items.items():
            out.append({"kind": kind, "name": name, "simulated": cls.simulated,
                        "implemented": cls.implemented, "note": cls.note})
    return out


__all__ = ["ProviderError", "NotConfigured", "get", "exists", "describe", "REGISTRY"]
