"""Abstract provider interfaces. The orchestrator only talks to these methods."""


class ProviderError(Exception):
    """Recoverable provider failure (timeout, 5xx...). The orchestrator retries then falls back to handover."""


class NotConfigured(ProviderError):
    """Raised by real-provider stubs that are not implemented / have no credentials."""


class Provider:
    kind = ""
    simulated = True      # True = fake, no external service involved
    implemented = True    # False = placeholder stub, not usable yet
    note = ""


class STTProvider(Provider):
    kind = "stt"

    def transcribe(self, audio, language, ctx):
        """audio: bytes (real) or str (simulated). Return {"text","confidence","latency_ms"}."""
        raise NotImplementedError


class LLMProvider(Provider):
    kind = "llm"

    def respond(self, ctx):
        """ctx: language, company, agent, history, user_text, knowledge, scenario, attempt.
        Return {"text","intent","handover","latency_ms"}."""
        raise NotImplementedError

    def summarize(self, ctx):
        raise NotImplementedError


class TTSProvider(Provider):
    kind = "tts"

    def synthesize(self, text, language, voice, ctx):
        """Return {"duration_ms","latency_ms"}."""
        raise NotImplementedError


class TelephonyProvider(Provider):
    kind = "telephony"

    def place_call(self, from_number, to_number, direction, ctx):
        """Return {"status": connected|no_answer|busy|failed, "sid"}."""
        raise NotImplementedError

    def transfer(self, sid, target):
        """Return {"status","sip_uri"}."""
        raise NotImplementedError
