from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import urlopen

from app.utils.exceptions import SourceExtractionError


MAX_FILE_SIZE_BYTES = 250 * 1024
MAX_INDEXED_FILES = 300
MAX_TOTAL_CHUNKS = 1200
MAX_TOTAL_TEXT_CHARS = 2_000_000
MAX_FILE_LINES = 100_000


@dataclass
class RepoRef:
    owner: str
    repo: str
    branch: Optional[str]
    canonical: str


def parse_github_url(url: str) -> RepoRef:
    """Parse a public GitHub repository URL into owner/repo/branch.

    Supports:
    - https://github.com/owner/repo
    - https://github.com/owner/repo/
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo/tree/branch-name
    - https://github.com/owner/repo/tree/feature/branch-name

    Rejects:
    - https://github.com/ (missing owner/repo)
    - https://github.com/owner (missing repo)
    - https://github.com/owner/ (missing repo)
    - URLs with /issues, /pull, /blob, etc. paths
    - Non-GitHub URLs
    """
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        raise SourceExtractionError(
            "Invalid GitHub repository URL. Please provide a public repository URL like https://github.com/owner/repo"
        )

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise SourceExtractionError(
            "Invalid GitHub repository URL. Please provide a public repository URL like https://github.com/owner/repo"
        )

    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    safe_name = re.compile(r"^[A-Za-z0-9_.-]+$")
    if not safe_name.match(owner) or not safe_name.match(repo):
        raise SourceExtractionError(
            "Invalid GitHub repository URL. Owner and repo must contain only letters, numbers, hyphens, underscores, and dots."
        )

    # Validate that owner and repo are not empty after removing .git
    if not owner or not repo:
        raise SourceExtractionError(
            "Invalid GitHub repository URL. Please provide a public repository URL like https://github.com/owner/repo"
        )

    branch: Optional[str] = None
    if len(parts) >= 4 and parts[2] == "tree":
        # /tree/branch-name is valid
        branch = "/".join(parts[3:])
    elif len(parts) > 2:
        # Reject URLs with paths like /issues, /pull, /blob, etc.
        invalid_paths = {"issues", "pull", "blob", "raw", "releases", "wiki", "discussions", "security"}
        if parts[2] in invalid_paths:
            raise SourceExtractionError(
                f"Invalid GitHub repository URL. The path /{parts[2]} is not supported. Please provide a repository URL like https://github.com/owner/repo or https://github.com/owner/repo/tree/branch"
            )
        # Any other unexpected path is treated as an error for safety
        if parts[2] != "":
            raise SourceExtractionError(
                f"Invalid GitHub repository URL. Please provide a repository URL like https://github.com/owner/repo or https://github.com/owner/repo/tree/branch"
            )

    canonical = f"https://github.com/{owner}/{repo}"
    return RepoRef(owner=owner, repo=repo, branch=branch, canonical=canonical)


def _run_git_clone(repo_url: str, dest: str, branch: Optional[str] = None) -> bool:
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [repo_url, dest]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        return True
    except Exception:
        return False


def _safe_extract_zip(zip_path: str, dest: str) -> None:
    dest_path = Path(dest).resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (dest_path / member.filename).resolve()
            if not str(target).startswith(str(dest_path) + os.sep) and target != dest_path:
                raise SourceExtractionError("Unsafe repository archive path detected.")
        archive.extractall(dest_path)


def _download_zip_archive(owner: str, repo: str, branch: Optional[str], dest: str) -> bool:
    branches = [branch] if branch else ["main", "master"]
    for branch_name in branches:
        url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch_name}.zip"
        tmp_zip = os.path.join(dest, "repo.zip")
        try:
            with urlopen(url, timeout=60) as resp:
                if getattr(resp, "status", 200) != 200:
                    continue
                with open(tmp_zip, "wb") as fh:
                    shutil.copyfileobj(resp, fh)
            _safe_extract_zip(tmp_zip, dest)
            os.remove(tmp_zip)
            children = [p for p in os.listdir(dest) if os.path.isdir(os.path.join(dest, p))]
            if children:
                inner = os.path.join(dest, children[0])
                for name in os.listdir(inner):
                    shutil.move(os.path.join(inner, name), os.path.join(dest, name))
                shutil.rmtree(inner, ignore_errors=True)
            return True
        except Exception:
            try:
                if os.path.exists(tmp_zip):
                    os.remove(tmp_zip)
            except Exception:
                pass
            continue
    return False


def fetch_repository(url: str, branch: Optional[str] = None) -> Tuple[str, RepoRef]:
    """Fetch a public repository into a temp directory. Caller must remove it."""
    ref = parse_github_url(url)
    if branch:
        ref.branch = branch

    tmpdir = tempfile.mkdtemp(prefix="sage_github_")
    dest = os.path.join(tmpdir, "repo")
    os.makedirs(dest, exist_ok=True)

    repo_url = f"https://github.com/{ref.owner}/{ref.repo}.git"
    if not _run_git_clone(repo_url, dest, ref.branch):
        if not _download_zip_archive(ref.owner, ref.repo, ref.branch, dest):
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise SourceExtractionError("Could not fetch repository. Ensure the repository exists and is public.")
    return dest, ref


_SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", ".venv", "venv", "__pycache__",
    ".pytest_cache", "coverage", ".idea", ".vscode", ".mypy_cache", ".ruff_cache", ".parcel-cache",
}

_IMPORTANT_FILES = {
    "Dockerfile", "README", "README.md", "requirements.txt", "package.json", "pyproject.toml",
    "pom.xml", "build.gradle", "gradle.properties", "composer.json", "Gemfile", "go.mod", "Cargo.toml",
}

_EXT_WHITELIST = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cpp", ".c", ".h", ".hpp", ".html",
    ".css", ".json", ".yaml", ".yml", ".md", ".sql", ".go", ".rs", ".php", ".rb",
    ".kt", ".swift", ".xml", ".toml", ".ini", ".env.example",
}

_LOCK_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock"}


def is_binary_file(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(8000)
            return b"\0" in chunk
    except Exception:
        return True


def scan_repository_files(
    root: str,
    max_file_size: int = MAX_FILE_SIZE_BYTES,
    max_files: int = MAX_INDEXED_FILES,
) -> Iterable[Tuple[str, str]]:
    """Yield (relative_path, extension) for safe text files to index."""
    yielded = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if yielded >= max_files:
                return
            if fname in _LOCK_FILES:
                continue
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, root).replace("\\", "/")
            try:
                if os.path.getsize(full) > max_file_size:
                    continue
            except Exception:
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext in _EXT_WHITELIST or fname in _IMPORTANT_FILES:
                if is_binary_file(full):
                    continue
                yielded += 1
                yield rel, ext or ""


def detect_language_by_ext(ext: str) -> str:
    m = ext.lower()
    if m == ".py": return "Python"
    if m in {".js", ".jsx"}: return "JavaScript"
    if m in {".ts", ".tsx"}: return "TypeScript"
    if m == ".java": return "Java"
    if m in {".cpp", ".c", ".h", ".hpp"}: return "C/C++"
    if m == ".md": return "Markdown"
    if m == ".json": return "JSON"
    if m == ".html": return "HTML"
    if m == ".css": return "CSS"
    if m == ".sql": return "SQL"
    if m == ".go": return "Go"
    if m == ".rs": return "Rust"
    if m == ".php": return "PHP"
    if m == ".rb": return "Ruby"
    if m == ".kt": return "Kotlin"
    if m == ".swift": return "Swift"
    if m in {".yaml", ".yml"}: return "YAML"
    if m == ".xml": return "XML"
    if m == ".toml": return "TOML"
    return "Text"


def read_file_lines(root: str, rel_path: str, max_lines: int = MAX_FILE_LINES) -> List[str]:
    full = os.path.join(root, rel_path)
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            return [line.rstrip("\n") for line in fh.readlines()[:max_lines]]
    except Exception:
        return []


def chunk_file_by_lines(lines: List[str], max_lines: int = 120, min_lines: int = 40) -> List[Tuple[int, int, str]]:
    """Return (start_line, end_line, text) chunks. Lines are 1-based."""
    chunks: list[Tuple[int, int, str]] = []
    i = 0
    total = len(lines)
    while i < total:
        j = min(i + max_lines, total)
        if total - i < min_lines and chunks:
            last_start, _, last_text = chunks[-1]
            chunks[-1] = (last_start, total, last_text + "\n" + "\n".join(lines[i:total]))
            break
        text = "\n".join(lines[i:j])
        if text.strip():
            chunks.append((i + 1, j, text))
        i = j
    return chunks


def generate_repository_overview(
    root: str,
    ref: RepoRef,
    detected_langs: set[str],
    files_indexed: int,
    files_skipped: int,
    total_chunks_created: int,
) -> str:
    """Generate a deterministic repository overview from metadata only (no LLM).
    
    Includes:
    - Repository metadata
    - Detected languages
    - Important files found
    - Directory structure preview
    - Entry points and special files detected
    """
    overview_parts = []
    
    # Header
    overview_parts.append(f"Repository: {ref.owner}/{ref.repo}")
    if ref.branch:
        overview_parts.append(f"Branch: {ref.branch}")
    overview_parts.append("")
    
    # Summary section
    overview_parts.append("SUMMARY")
    overview_parts.append("=" * 60)
    overview_parts.append(f"Detected Languages: {', '.join(sorted(detected_langs)) if detected_langs else 'None'}")
    overview_parts.append(f"Files Indexed: {files_indexed}")
    overview_parts.append(f"Files Skipped: {files_skipped}")
    overview_parts.append(f"Total Chunks Created: {total_chunks_created}")
    overview_parts.append("")
    
    # Top-level directories
    top_dirs = set()
    try:
        for entry in os.listdir(root):
            if entry.startswith("."):
                continue
            full_path = os.path.join(root, entry)
            if os.path.isdir(full_path) and entry not in _SKIP_DIRS:
                top_dirs.add(entry)
    except Exception:
        pass
    
    if top_dirs:
        overview_parts.append("STRUCTURE")
        overview_parts.append("=" * 60)
        overview_parts.append(f"Top-level Directories: {', '.join(sorted(top_dirs))}")
        overview_parts.append("")
    
    # Important files section
    important_file_patterns = {
        "README": ["README.md", "README", "readme.md"],
        "Requirements": ["requirements.txt", "Pipfile", "poetry.lock", "package.json", "Gemfile"],
        "Setup": ["setup.py", "setup.cfg", "pyproject.toml", "Dockerfile", "docker-compose.yml", "Makefile"],
        "Config": [".env.example", ".env", "config.yml", "config.yaml", "settings.py", "config.json"],
        "Tests": ["tests/", "__tests__/", "test_", "spec/", ".test."],
        "Main Entry Points": ["main.py", "app.py", "server.py", "index.js", "index.ts", "index.jsx", "main.go", "Main.java"],
        "Routes/Controllers": ["routes/", "router.py", "controller/", "controllers/", "endpoints/"],
        "Models/Schemas": ["models/", "schema/", "schemas/", "entities/", "models.py"],
        "Services": ["services/", "utils/", "helpers/"],
        "Configs": ["configs/", "config/", ".github/"],
    }
    
    overview_parts.append("IMPORTANT FILES & DIRECTORIES")
    overview_parts.append("=" * 60)
    
    files_found = {}
    for category, patterns in important_file_patterns.items():
        found = []
        for pattern in patterns:
            check_path = os.path.join(root, pattern)
            if os.path.exists(check_path):
                found.append(pattern)
        if found:
            files_found[category] = found
    
    if files_found:
        for category, items in files_found.items():
            status_items = []
            for item in items:
                status_items.append(f"✓ {item}")
            overview_parts.append(f"{category}: {', '.join(status_items)}")
    else:
        overview_parts.append("(No recognized important files/directories found)")
    
    overview_parts.append("")
    
    # Directory tree preview (depth 1-2)
    overview_parts.append("DIRECTORY TREE (Preview)")
    overview_parts.append("=" * 60)
    
    try:
        tree_lines = []
        entries = sorted(os.listdir(root))
        for i, entry in enumerate(entries[:15]):  # Limit to first 15 top-level items
            if entry.startswith("."):
                continue
            full_path = os.path.join(root, entry)
            is_last = (i == len(entries) - 1)
            prefix = "└── " if is_last else "├── "
            
            if os.path.isdir(full_path) and entry not in _SKIP_DIRS:
                tree_lines.append(f"{prefix}{entry}/")
                # Add one level deeper
                try:
                    sub_entries = sorted(os.listdir(full_path))[:5]  # Limit sub-entries
                    for j, sub_entry in enumerate(sub_entries):
                        if sub_entry.startswith("."):
                            continue
                        sub_full = os.path.join(full_path, sub_entry)
                        is_sub_last = (j == len(sub_entries) - 1)
                        sub_prefix = "    └── " if is_sub_last else "    ├── "
                        if os.path.isdir(sub_full):
                            tree_lines.append(f"{sub_prefix}{sub_entry}/")
                        else:
                            tree_lines.append(f"{sub_prefix}{sub_entry}")
                except Exception:
                    pass
            else:
                tree_lines.append(f"{prefix}{entry}")
        
        if tree_lines:
            overview_parts.extend(tree_lines)
        else:
            overview_parts.append("(No files to display)")
    except Exception:
        overview_parts.append("(Could not generate tree preview)")
    
    overview_parts.append("")
    overview_parts.append("This overview was automatically generated from repository metadata.")
    overview_parts.append("For detailed information, refer to individual source files.")
    
    return "\n".join(overview_parts)
