class BaseASRAdapter:
    name = "base"

    def transcribe(self, audio_path, target_text=""):
        raise NotImplementedError
