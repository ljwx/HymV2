import unittest

from hym.core.models import (
    ActionStatus,
    ActivityInfo,
    ArtifactRef,
    Observation,
    ObservationResult,
    UiTreeSource,
)
from hym.runtime.diagnostics import DiagnosticsService


class StubSession:
    def __init__(self):
        self.request = None

    def observe(self, request):
        self.request = request
        return ObservationResult(
            ActionStatus.SUCCESS,
            observation=Observation("device-1", ActivityInfo("com.example", "MainActivity")),
        )


class StubArtifacts:
    def save_bytes(self, *, kind, content, media_type, name_hint=None):
        return ArtifactRef("artifact-1", kind, "/tmp/artifact", media_type)


class DiagnosticsServiceTest(unittest.TestCase):
    def test_capture_uses_backend_default_ui_tree(self):
        session = StubSession()

        DiagnosticsService(session, StubArtifacts()).capture("failure")

        self.assertEqual(UiTreeSource.AUTO, session.request.ui_tree_source)


if __name__ == "__main__":
    unittest.main()
