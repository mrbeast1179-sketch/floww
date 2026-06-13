"""
Tests for scripts/start_incident.py

Run with:
    python -m pytest backend/tests/services/test_start_incident.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

# Ensure the scripts directory is importable.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import start_incident as si


@pytest.fixture(autouse=True)
def _clear_registry():
    """Reset the in-process idempotency registry before each test."""
    si._created_registry.clear()
    yield
    si._created_registry.clear()


@pytest.fixture
def tmp_incidents_dir(tmp_path):
    """
    Point start_incident's INCIDENTS_DIR and TEMPLATE_PATH at a temporary
    directory so tests don't touch the real repo.
    """
    incidents_dir = tmp_path / "INCIDENTS"
    incidents_dir.mkdir()
    template_path = incidents_dir / "_template.md"
    template_path.write_text(
        "# {{DATE}}: {{TITLE}}\n"
        "## Severity\n{{SEVERITY}}\n"
        "## Detection\n"
        "Alert: {{ALERT_ID}} | Category: {{CATEGORY}} | Name: {{ALERT_NAME}}\n"
        "Details: {{DETECTION_DETAILS}}\n"
        "## Timeline\n{{TIMESTAMP}}\n"
        "## Root Cause\n{{ROOT_CAUSE}}\n"
        "## Remediation\nImmediate: {{IMMEDIATE_ACTIONS}}\nPermanent: {{PERMANENT_FIX}}\n"
        "## Action Items\n{{ACTION_ITEM_1}} -> {{KANBAN_ID_1}}\n"
        "## Lessons Learned\n{{LESSONS_LEARNED}}\n",
        encoding="utf-8",
    )
    with patch.object(si, "INCIDENTS_DIR", incidents_dir), \
         patch.object(si, "TEMPLATE_PATH", template_path):
        yield incidents_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTemplateRendering:
    """Verify that placeholders are correctly replaced."""

    def test_all_placeholders_replaced(self, tmp_incidents_dir):
        path = si.create_from_alert(
            "ALERT-001",
            title="DB failover",
            severity="CRITICAL",
            category="infra",
            alert_name="Primary DB down",
        )
        content = path.read_text(encoding="utf-8")
        # No raw placeholders should remain.
        assert "{{" not in content
        assert "}}" not in content

    def test_title_and_severity_in_output(self, tmp_incidents_dir):
        path = si.create_from_alert(
            "ALERT-002",
            title="API latency spike",
            severity="MEDIUM",
            category="app",
        )
        content = path.read_text(encoding="utf-8")
        assert "API latency spike" in content
        assert "MEDIUM" in content

    def test_alert_id_and_category_in_detection(self, tmp_incidents_dir):
        path = si.create_from_alert(
            "ALERT-003",
            title="Cache miss surge",
            severity="LOW",
            category="data",
            alert_name="Redis cache miss rate high",
        )
        content = path.read_text(encoding="utf-8")
        assert "ALERT-003" in content
        assert "data" in content
        assert "Redis cache miss rate high" in content


class TestFileCreation:
    """Verify that files are created with the correct name and location."""

    def test_file_is_created_in_incidents_dir(self, tmp_incidents_dir):
        path = si.create_from_alert("ALERT-010", title="Disk full")
        assert path.exists()
        assert path.parent == tmp_incidents_dir

    def test_filename_uses_date_and_slug(self, tmp_incidents_dir):
        path = si.create_from_alert("ALERT-011", title="Network Partition!")
        today = si._today()
        assert path.name.startswith(today + "_")
        assert path.name.endswith(".md")
        # Slug should be lowercase, no special chars.
        slug_part = path.stem.split("_", 1)[1]
        assert slug_part == slug_part.lower()
        assert " " not in slug_part

    def test_return_type_is_path(self, tmp_incidents_dir):
        result = si.create_from_alert("ALERT-012", title="Test")
        assert isinstance(result, Path)


class TestIdempotency:
    """Calling create_from_alert with the same alert_id should not duplicate."""

    def test_same_alert_id_returns_existing_file(self, tmp_incidents_dir):
        path1 = si.create_from_alert("ALERT-020", title="OOM kill")
        path2 = si.create_from_alert("ALERT-020", title="OOM kill")
        assert path1 == path2

    def test_no_duplicate_files_created(self, tmp_incidents_dir):
        si.create_from_alert("ALERT-021", title="OOM kill again")
        si.create_from_alert("ALERT-021", title="OOM kill again")
        md_files = list(tmp_incidents_dir.glob("*.md"))
        # Only one incident file (plus the template).
        incident_files = [f for f in md_files if f.name != "_template.md"]
        assert len(incident_files) == 1

    def test_different_alert_ids_create_different_files(self, tmp_incidents_dir):
        path1 = si.create_from_alert("ALERT-022", title="Incident A")
        path2 = si.create_from_alert("ALERT-023", title="Incident B")
        assert path1 != path2


class TestDirectoryCreation:
    """The INCIDENTS directory should be created if it doesn't exist."""

    def test_creates_directory_when_missing(self, tmp_path):
        incidents_dir = tmp_path / "INCIDENTS"
        # Template is in the real repo, not in tmp — patch TEMPLATE_PATH to point to a temp template
        _real_template = Path(__file__).resolve().parents[3] / "docs" / "INCIDENTS" / "_template.md"
        with patch.object(si, "INCIDENTS_DIR", incidents_dir):
            # Don't create the directory — the function should do it
            assert not incidents_dir.exists()
            path = si.create_from_alert("ALERT-030", title="Dir test")
            assert path.exists()
            assert incidents_dir.exists()


class TestValidation:
    """Invalid inputs should raise ValueError."""

    def test_invalid_severity_raises(self, tmp_incidents_dir):
        with pytest.raises(ValueError, match="Invalid severity"):
            si.create_from_alert("ALERT-040", title="Bad sev", severity="HIGH")

    def test_invalid_category_raises(self, tmp_incidents_dir):
        with pytest.raises(ValueError, match="Invalid category"):
            si.create_from_alert("ALERT-041", title="Bad cat", category="bogus")


class TestSlugify:
    """Unit tests for the _slugify helper."""

    def test_spaces_to_hyphens(self):
        assert si._slugify("Hello World") == "hello-world"

    def test_special_chars_stripped(self):
        # Underscore is stripped by the regex (not in [^a-z0-9\s-]), so DB_Failover → dbfailover
        assert si._slugify("DB_Failover! (urgent)") == "dbfailover-urgent"

    def test_multiple_spaces_collapsed(self):
        assert si._slugify("a   b    c") == "a-b-c"
