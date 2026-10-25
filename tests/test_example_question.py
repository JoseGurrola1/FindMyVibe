import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import example_question
from gemini_questions import NextQuestion


class ExampleEnvironmentTests(unittest.TestCase):
    def run_with_local_env(self, existing_key=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script_dir = root / "project"
            script_dir.mkdir()
            (script_dir / ".env").write_text("GEMINI_API_KEY=file-fixture\n", encoding="utf-8")
            terminal_dir = root / "elsewhere"
            terminal_dir.mkdir()
            (terminal_dir / ".env").write_text("GEMINI_API_KEY=wrong-directory-fixture\n", encoding="utf-8")
            previous_cwd = Path.cwd()
            try:
                os.chdir(terminal_dir)
                environment = {} if existing_key is None else {"GEMINI_API_KEY": existing_key}
                with (
                    patch.dict(os.environ, environment, clear=True),
                    patch.object(example_question, "__file__", str(script_dir / "example_question.py")),
                    patch.object(example_question, "generate_next_question") as generate,
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    def mocked_generation(session):
                        self.assertEqual(os.environ["GEMINI_API_KEY"], existing_key or "file-fixture")
                        return NextQuestion(
                            question="What atmosphere would you prefer?",
                            options=["Quiet", "Lively"],
                            target_attribute="atmosphere",
                        )

                    generate.side_effect = mocked_generation
                    self.assertEqual(example_question.main(), 0)
                    generate.assert_called_once()
            finally:
                os.chdir(previous_cwd)

    def test_loads_script_relative_env_before_generation(self):
        self.run_with_local_env()

    def test_existing_process_value_is_preserved(self):
        self.run_with_local_env(existing_key="process-fixture")


if __name__ == "__main__":
    unittest.main()
