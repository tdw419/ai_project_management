import pytest
from pathlib import Path
from src.ouroboros.core.code_applier import CodeApplier

@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace for testing."""
    return tmp_path

class TestCodeApplier:
    def test_init(self, temp_workspace):
        applier = CodeApplier(temp_workspace)
        assert applier.workspace_path == temp_workspace

    def test_apply_single_file(self, temp_workspace):
        applier = CodeApplier(temp_workspace)
        code_changes = {"test.py": "print('hello world')"}
        
        applier.apply(code_changes)
        
        file_path = temp_workspace / "test.py"
        assert file_path.exists()
        assert file_path.read_text() == "print('hello world')"

    def test_apply_multiple_files(self, temp_workspace):
        applier = CodeApplier(temp_workspace)
        code_changes = {
            "file1.py": "content1",
            "file2.txt": "content2"
        }
        
        applier.apply(code_changes)
        
        assert (temp_workspace / "file1.py").read_text() == "content1"
        assert (temp_workspace / "file2.txt").read_text() == "content2"

    def test_apply_with_subdirectories(self, temp_workspace):
        applier = CodeApplier(temp_workspace)
        code_changes = {
            "src/module/utils.py": "def util(): pass",
            "tests/test_utils.py": "import utils"
        }
        
        applier.apply(code_changes)
        
        utils_path = temp_workspace / "src" / "module" / "utils.py"
        test_path = temp_workspace / "tests" / "test_utils.py"
        
        assert utils_path.exists()
        assert test_path.exists()
        assert utils_path.read_text() == "def util(): pass"
        assert test_path.read_text() == "import utils"

    def test_apply_overwrite_existing_file(self, temp_workspace):
        applier = CodeApplier(temp_workspace)
        file_path = temp_workspace / "existing.py"
        file_path.write_text("old content")
        
        code_changes = {"existing.py": "new content"}
        applier.apply(code_changes)
        
        assert file_path.read_text() == "new content"
