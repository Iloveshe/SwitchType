import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path


SCRIPT_PATH = Path("bench/scripts/run_sensevoice.py")


def load_script_module():
    spec = importlib.util.spec_from_file_location("run_sensevoice", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RunSenseVoiceTests(unittest.TestCase):
    def test_runs_automodel_and_writes_postprocessed_text(self):
        calls = []

        class FakeAutoModel:
            def __init__(self, **kwargs):
                calls.append(("init", kwargs))

            def generate(self, **kwargs):
                calls.append(("generate", kwargs))
                return [{"text": "<|zh|><|NEUTRAL|><|Speech|><|withitn|>扣德克斯 PR"}]

        funasr = types.ModuleType("funasr")
        funasr.AutoModel = FakeAutoModel
        utils = types.ModuleType("funasr.utils")
        postprocess = types.ModuleType("funasr.utils.postprocess_utils")
        postprocess.rich_transcription_postprocess = lambda text: text.replace(
            "<|zh|><|NEUTRAL|><|Speech|><|withitn|>",
            "",
        )
        original_modules = {
            name: sys.modules.get(name)
            for name in ["funasr", "funasr.utils", "funasr.utils.postprocess_utils"]
        }
        sys.modules["funasr"] = funasr
        sys.modules["funasr.utils"] = utils
        sys.modules["funasr.utils.postprocess_utils"] = postprocess
        try:
            module = load_script_module()
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                audio = root / "sample.wav"
                output = root / "transcript.txt"
                audio.write_bytes(b"placeholder")

                code = module.main(
                    [
                        "--model",
                        "iic/SenseVoiceSmall",
                        "--audio",
                        str(audio),
                        "--output",
                        str(output),
                        "--device",
                        "cpu",
                    ]
                )
                output_text = output.read_text(encoding="utf-8")
        finally:
            for name, original in original_modules.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

        self.assertEqual(code, 0)
        self.assertEqual(output_text, "扣德克斯 PR\n")
        self.assertEqual(calls[0][0], "init")
        self.assertEqual(calls[0][1]["model"], "iic/SenseVoiceSmall")
        self.assertEqual(calls[0][1]["device"], "cpu")
        self.assertEqual(calls[1][0], "generate")
        self.assertEqual(calls[1][1]["input"], str(audio))
        self.assertEqual(calls[1][1]["language"], "auto")
        self.assertTrue(calls[1][1]["use_itn"])

    def test_cache_dir_sets_modelscope_environment_before_model_init(self):
        observed_environment = {}

        class FakeAutoModel:
            def __init__(self, **kwargs):
                observed_environment["MODELSCOPE_CACHE"] = os.environ.get("MODELSCOPE_CACHE")
                observed_environment["MODELSCOPE_CREDENTIALS_PATH"] = os.environ.get("MODELSCOPE_CREDENTIALS_PATH")

            def generate(self, **kwargs):
                return [{"text": "ok"}]

        funasr = types.ModuleType("funasr")
        funasr.AutoModel = FakeAutoModel
        utils = types.ModuleType("funasr.utils")
        postprocess = types.ModuleType("funasr.utils.postprocess_utils")
        postprocess.rich_transcription_postprocess = lambda text: text
        original_modules = {
            name: sys.modules.get(name)
            for name in ["funasr", "funasr.utils", "funasr.utils.postprocess_utils"]
        }
        original_environment = {
            "MODELSCOPE_CACHE": os.environ.get("MODELSCOPE_CACHE"),
            "MODELSCOPE_CREDENTIALS_PATH": os.environ.get("MODELSCOPE_CREDENTIALS_PATH"),
        }
        sys.modules["funasr"] = funasr
        sys.modules["funasr.utils"] = utils
        sys.modules["funasr.utils.postprocess_utils"] = postprocess
        try:
            module = load_script_module()
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                audio = root / "sample.wav"
                output = root / "transcript.txt"
                cache = root / "modelscope-cache"
                audio.write_bytes(b"placeholder")

                code = module.main(
                    [
                        "--model",
                        "iic/SenseVoiceSmall",
                        "--audio",
                        str(audio),
                        "--output",
                        str(output),
                        "--cache-dir",
                        str(cache),
                    ]
                )
        finally:
            for name, original in original_modules.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original
            for name, original in original_environment.items():
                if original is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = original

        self.assertEqual(code, 0)
        self.assertEqual(observed_environment["MODELSCOPE_CACHE"], str(cache))
        self.assertEqual(observed_environment["MODELSCOPE_CREDENTIALS_PATH"], str(cache / "credentials"))

    def test_huggingface_hub_uses_cache_and_passes_hub_to_automodel(self):
        calls = []
        observed_environment = {}

        class FakeAutoModel:
            def __init__(self, **kwargs):
                calls.append(("init", kwargs))
                observed_environment["HF_HOME"] = os.environ.get("HF_HOME")
                observed_environment["HUGGINGFACE_HUB_CACHE"] = os.environ.get("HUGGINGFACE_HUB_CACHE")

            def generate(self, **kwargs):
                return [{"text": "ok"}]

        funasr = types.ModuleType("funasr")
        funasr.AutoModel = FakeAutoModel
        utils = types.ModuleType("funasr.utils")
        postprocess = types.ModuleType("funasr.utils.postprocess_utils")
        postprocess.rich_transcription_postprocess = lambda text: text
        original_modules = {
            name: sys.modules.get(name)
            for name in ["funasr", "funasr.utils", "funasr.utils.postprocess_utils"]
        }
        original_environment = {
            "HF_HOME": os.environ.get("HF_HOME"),
            "HUGGINGFACE_HUB_CACHE": os.environ.get("HUGGINGFACE_HUB_CACHE"),
        }
        sys.modules["funasr"] = funasr
        sys.modules["funasr.utils"] = utils
        sys.modules["funasr.utils.postprocess_utils"] = postprocess
        try:
            module = load_script_module()
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                audio = root / "sample.wav"
                output = root / "transcript.txt"
                cache = root / "cache"
                audio.write_bytes(b"placeholder")

                code = module.main(
                    [
                        "--model",
                        "FunAudioLLM/SenseVoiceSmall",
                        "--hub",
                        "hf",
                        "--audio",
                        str(audio),
                        "--output",
                        str(output),
                        "--cache-dir",
                        str(cache),
                    ]
                )
        finally:
            for name, original in original_modules.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original
            for name, original in original_environment.items():
                if original is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = original

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][1]["model"], "FunAudioLLM/SenseVoiceSmall")
        self.assertEqual(calls[0][1]["hub"], "hf")
        self.assertEqual(observed_environment["HF_HOME"], str(cache / "huggingface"))
        self.assertEqual(observed_environment["HUGGINGFACE_HUB_CACHE"], str(cache / "huggingface" / "hub"))

    def test_vad_model_none_disables_vad_model_kwargs(self):
        calls = []

        class FakeAutoModel:
            def __init__(self, **kwargs):
                calls.append(("init", kwargs))

            def generate(self, **kwargs):
                return [{"text": "ok"}]

        funasr = types.ModuleType("funasr")
        funasr.AutoModel = FakeAutoModel
        utils = types.ModuleType("funasr.utils")
        postprocess = types.ModuleType("funasr.utils.postprocess_utils")
        postprocess.rich_transcription_postprocess = lambda text: text
        original_modules = {
            name: sys.modules.get(name)
            for name in ["funasr", "funasr.utils", "funasr.utils.postprocess_utils"]
        }
        sys.modules["funasr"] = funasr
        sys.modules["funasr.utils"] = utils
        sys.modules["funasr.utils.postprocess_utils"] = postprocess
        try:
            module = load_script_module()
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                audio = root / "sample.wav"
                output = root / "transcript.txt"
                audio.write_bytes(b"placeholder")

                code = module.main(
                    [
                        "--model",
                        "FunAudioLLM/SenseVoiceSmall",
                        "--hub",
                        "hf",
                        "--vad-model",
                        "none",
                        "--audio",
                        str(audio),
                        "--output",
                        str(output),
                    ]
                )
        finally:
            for name, original in original_modules.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

        self.assertEqual(code, 0)
        self.assertIsNone(calls[0][1]["vad_model"])
        self.assertIsNone(calls[0][1]["vad_kwargs"])


if __name__ == "__main__":
    unittest.main()
