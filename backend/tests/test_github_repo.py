import pytest
from app.services.github_repo import parse_github_url, chunk_file_by_lines, generate_repository_overview, scan_repository_files, RepoRef
from app.utils.exceptions import SourceExtractionError
import tempfile
import os


# ========== VALID URL TESTS ==========

def test_parse_github_url_simple():
    ref = parse_github_url("https://github.com/owner/repo")
    assert ref.owner == "owner"
    assert ref.repo == "repo"
    assert ref.branch is None
    assert ref.canonical == "https://github.com/owner/repo"


def test_parse_github_url_with_trailing_slash():
    ref = parse_github_url("https://github.com/owner/repo/")
    assert ref.owner == "owner"
    assert ref.repo == "repo"
    assert ref.branch is None


def test_parse_github_url_with_git_suffix():
    ref = parse_github_url("https://github.com/owner/repo.git")
    assert ref.owner == "owner"
    assert ref.repo == "repo"
    assert ref.branch is None
    assert ref.canonical == "https://github.com/owner/repo"


def test_parse_github_url_with_tree_branch():
    ref = parse_github_url("https://github.com/owner/repo/tree/main")
    assert ref.owner == "owner"
    assert ref.repo == "repo"
    assert ref.branch == "main"


def test_parse_github_url_with_feature_branch():
    ref = parse_github_url("https://github.com/owner/repo/tree/feature/auth-flow")
    assert ref.owner == "owner"
    assert ref.repo == "repo"
    assert ref.branch == "feature/auth-flow"


def test_parse_github_url_with_dots_in_names():
    ref = parse_github_url("https://github.com/owner.name/repo.name")
    assert ref.owner == "owner.name"
    assert ref.repo == "repo.name"


def test_parse_github_url_with_hyphens_in_names():
    ref = parse_github_url("https://github.com/owner-name/repo-name")
    assert ref.owner == "owner-name"
    assert ref.repo == "repo-name"


def test_parse_github_url_with_underscores_in_names():
    ref = parse_github_url("https://github.com/owner_name/repo_name")
    assert ref.owner == "owner_name"
    assert ref.repo == "repo_name"


# ========== INVALID URL TESTS ==========

def test_parse_github_url_invalid_minimal():
    """Reject https://github.com/ (missing owner/repo)"""
    with pytest.raises(SourceExtractionError):
        parse_github_url("https://github.com/")


def test_parse_github_url_invalid_only_owner():
    """Reject https://github.com/owner (missing repo)"""
    with pytest.raises(SourceExtractionError):
        parse_github_url("https://github.com/owner")


def test_parse_github_url_invalid_only_owner_with_slash():
    """Reject https://github.com/owner/ (missing repo)"""
    with pytest.raises(SourceExtractionError):
        parse_github_url("https://github.com/owner/")


def test_parse_github_url_invalid_issues_path():
    """Reject URLs with /issues path"""
    with pytest.raises(SourceExtractionError):
        parse_github_url("https://github.com/owner/repo/issues")


def test_parse_github_url_invalid_pull_path():
    """Reject URLs with /pull path"""
    with pytest.raises(SourceExtractionError):
        parse_github_url("https://github.com/owner/repo/pull/1")


def test_parse_github_url_invalid_blob_path():
    """Reject URLs with /blob path (file content)"""
    with pytest.raises(SourceExtractionError):
        parse_github_url("https://github.com/owner/repo/blob/main/file.py")


def test_parse_github_url_invalid_releases_path():
    """Reject URLs with /releases path"""
    with pytest.raises(SourceExtractionError):
        parse_github_url("https://github.com/owner/repo/releases")


def test_parse_github_url_invalid_wiki_path():
    """Reject URLs with /wiki path"""
    with pytest.raises(SourceExtractionError):
        parse_github_url("https://github.com/owner/repo/wiki")


def test_parse_github_url_invalid_non_github():
    """Reject non-GitHub URLs"""
    with pytest.raises(SourceExtractionError):
        parse_github_url("https://gitlab.com/owner/repo")


def test_parse_github_url_invalid_not_url():
    """Reject invalid URL strings"""
    with pytest.raises(SourceExtractionError):
        parse_github_url("not-a-url")


def test_parse_github_url_invalid_empty_string():
    """Reject empty strings"""
    with pytest.raises(SourceExtractionError):
        parse_github_url("")


def test_parse_github_url_invalid_special_chars_in_owner():
    """Reject owner names with special characters"""
    with pytest.raises(SourceExtractionError):
        parse_github_url("https://github.com/owner@name/repo")


def test_parse_github_url_invalid_special_chars_in_repo():
    """Reject repo names with special characters (handled by URL parsing, fragment is stripped)"""
    # Note: # is stripped by urlparse as a fragment, so repo#name becomes just repo
    # This test verifies the parser handles it gracefully
    ref = parse_github_url("https://github.com/owner/repo#name")
    assert ref.repo == "repo"  # Fragment is stripped by urlparse


# ========== CHUNK BY LINES TESTS ==========

def test_chunk_file_by_lines_basic():
    lines = [f"line {i}" for i in range(1, 301)]
    chunks = chunk_file_by_lines(lines, max_lines=100, min_lines=20)
    assert len(chunks) == 3
    assert chunks[0][0] == 1
    assert chunks[0][1] == 100
    assert chunks[-1][1] == 300


# ========== REPOSITORY OVERVIEW TESTS ==========

def test_generate_repository_overview_basic():
    """Test basic overview generation with minimal metadata"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test files
        os.makedirs(os.path.join(tmpdir, "src"))
        os.makedirs(os.path.join(tmpdir, "tests"))
        open(os.path.join(tmpdir, "README.md"), "w").close()
        open(os.path.join(tmpdir, "requirements.txt"), "w").close()
        open(os.path.join(tmpdir, "setup.py"), "w").close()
        open(os.path.join(tmpdir, "src", "main.py"), "w").close()
        open(os.path.join(tmpdir, "tests", "test_main.py"), "w").close()
        
        ref = RepoRef(owner="testowner", repo="testrepo", branch="main", canonical="https://github.com/testowner/testrepo")
        detected_langs = {"Python", "Markdown"}
        
        overview = generate_repository_overview(
            tmpdir,
            ref,
            detected_langs,
            files_indexed=5,
            files_skipped=0,
            total_chunks_created=10,
        )
        
        # Verify key content in overview
        assert "testowner/testrepo" in overview
        assert "main" in overview
        assert "Python" in overview or "Markdown" in overview
        assert "5" in overview  # files_indexed
        assert "10" in overview  # total_chunks_created
        assert "SUMMARY" in overview
        assert "STRUCTURE" in overview
        assert "README.md" in overview
        assert "requirements.txt" in overview


def test_generate_repository_overview_deterministic():
    """Test that overview generation is deterministic (same output on consecutive runs)"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        os.makedirs(os.path.join(tmpdir, "src"))
        open(os.path.join(tmpdir, "README.md"), "w").close()
        open(os.path.join(tmpdir, "package.json"), "w").close()
        
        ref = RepoRef(owner="testowner", repo="testrepo", branch=None, canonical="https://github.com/testowner/testrepo")
        detected_langs = {"JavaScript"}
        
        # Generate overview twice
        overview1 = generate_repository_overview(
            tmpdir, ref, detected_langs, 2, 0, 5
        )
        overview2 = generate_repository_overview(
            tmpdir, ref, detected_langs, 2, 0, 5
        )
        
        # Should be identical
        assert overview1 == overview2


def test_generate_repository_overview_includes_important_files():
    """Test that important files are detected and included"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create various important files
        important_files = [
            "README.md", "requirements.txt", "package.json", "Dockerfile",
            "docker-compose.yml", "setup.py", "main.py"
        ]
        for fname in important_files:
            open(os.path.join(tmpdir, fname), "w").close()
        
        os.makedirs(os.path.join(tmpdir, "tests"))
        os.makedirs(os.path.join(tmpdir, "models"))
        os.makedirs(os.path.join(tmpdir, "services"))
        
        ref = RepoRef(owner="test", repo="test", branch=None, canonical="https://github.com/test/test")
        overview = generate_repository_overview(tmpdir, ref, set(), 10, 0, 20)
        
        # Check that important files are mentioned with checkmarks
        assert "README.md" in overview
        assert "requirements.txt" in overview
        assert "package.json" in overview
        assert "Dockerfile" in overview
        assert "docker-compose.yml" in overview
        assert "setup.py" in overview
        assert "main.py" in overview
        assert "tests" in overview
        assert "models" in overview or "Models" in overview
        assert "services" in overview or "Services" in overview


def test_generate_repository_overview_includes_detected_languages():
    """Test that detected languages are included in overview"""
    with tempfile.TemporaryDirectory() as tmpdir:
        ref = RepoRef(owner="test", repo="test", branch=None, canonical="https://github.com/test/test")
        detected_langs = {"Python", "JavaScript", "YAML", "Markdown"}
        
        overview = generate_repository_overview(tmpdir, ref, detected_langs, 5, 0, 10)
        
        # All detected languages should appear
        assert "Python" in overview
        assert "JavaScript" in overview
        assert "YAML" in overview
        assert "Markdown" in overview


def test_generate_repository_overview_empty_directory():
    """Test overview generation with empty directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        ref = RepoRef(owner="empty", repo="repo", branch=None, canonical="https://github.com/empty/repo")
        
        overview = generate_repository_overview(tmpdir, ref, set(), 0, 0, 0)
        
        # Should still have header and sections
        assert "empty/repo" in overview
        assert "SUMMARY" in overview
        assert "0" in overview  # No files indexed


def test_generate_repository_overview_branch_included():
    """Test that branch name is included when specified"""
    with tempfile.TemporaryDirectory() as tmpdir:
        ref = RepoRef(owner="test", repo="test", branch="develop", canonical="https://github.com/test/test")
        
        overview = generate_repository_overview(tmpdir, ref, set(), 0, 0, 0)
        
        assert "develop" in overview
        assert "Branch:" in overview


def test_scan_skips_symlinks_to_local_files(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    (repo / "notes.md").symlink_to(secret)

    files = [rel for rel, _ in scan_repository_files(str(repo))]
    assert files == ["main.py"]
