"""Configuration documents; callers decide when discarding or overwriting is allowed."""

from pathlib import Path

from ..configuration import load_config, save_config
from .editing import ConfigurationDraft, EditorController


def resolve_path(text: str) -> Path:
    if not text.strip():
        raise ValueError("Enter a file path")
    return Path(text.strip()).expanduser().resolve()


class DocumentController:
    def __init__(self) -> None:
        self.editor = EditorController()
        self.path: Path | None = None
        self._saved_revision = 0

    @property
    def dirty(self) -> bool:
        return self.editor.revision != self._saved_revision

    def new(self) -> None:
        self.editor = EditorController()
        self.path = None
        self._saved_revision = 0

    def load(self, path: Path) -> None:
        config = load_config(path)
        editor = EditorController(ConfigurationDraft.from_config(config))
        self.editor, self.path, self._saved_revision = editor, path, 0

    def save(self, path: Path) -> None:
        if self.editor.config is None:
            raise ValueError("Complete the configuration before saving")
        save_config(self.editor.config, path)
        self.path = path
        self._saved_revision = self.editor.revision
