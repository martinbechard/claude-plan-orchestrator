# langgraph_pipeline/shared/git.py
# Git stash, worktree management, and commit helpers shared across pipeline scripts.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md

"""Git operation helpers: stash, worktree lifecycle, artifact copy, and commit utilities."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from langgraph_pipeline.shared.paths import STATUS_FILE_PATH

# ─── Constants ────────────────────────────────────────────────────────────────

ORCHESTRATOR_STASH_MESSAGE = "orchestrator-auto-stash"
STASH_EXCLUDE_PLANS_PATHSPEC = ":(exclude).claude/plans/"
WORKTREE_BASE_DIR = ".worktrees"

# Coordination paths never copied from worktrees (owned by orchestrator)
_WORKTREE_SKIP_PREFIXES = (
    ".claude/plans/",
    ".claude/subagent-status/",
    ".claude/agent-claims",
)

# ─── Stash Helpers ────────────────────────────────────────────────────────────


def git_stash_working_changes() -> bool:
    """Stash any uncommitted working-tree changes before running an agent task.

    Returns True if a stash was created, False if the tree was already clean
    or if the stash command failed.
    """
    diff_result = subprocess.run(
        ["git", "diff", "--quiet"],
        capture_output=True
    )
    cached_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        capture_output=True
    )
    untracked_result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True
    )

    tree_is_clean = (
        diff_result.returncode == 0
        and cached_result.returncode == 0
        and untracked_result.stdout.strip() == b""
    )

    if tree_is_clean:
        return False

    stash_result = subprocess.run(
        [
            "git", "stash", "push", "--include-untracked",
            "-m", ORCHESTRATOR_STASH_MESSAGE,
            "--", ".", STASH_EXCLUDE_PLANS_PATHSPEC,
        ],
        capture_output=True
    )

    if stash_result.returncode == 0:
        print("[Stashed working-tree changes before task]")
        return True

    print("[Warning: git stash push failed - proceeding without stash]")
    return False


def git_stash_pop() -> bool:
    """Restore stashed working-tree changes after an agent task completes.

    Returns True on success, False if the pop failed (stash dropped, tree reset to HEAD).
    """
    # Discard task-status.json before pop to prevent merge conflict.
    # The file is ephemeral: its content was already consumed by read_status_file().
    if os.path.exists(STATUS_FILE_PATH):
        subprocess.run(
            ["git", "checkout", "--", STATUS_FILE_PATH],
            capture_output=True
        )

    result = subprocess.run(
        ["git", "stash", "pop"],
        capture_output=True
    )

    if result.returncode == 0:
        print("[Restored stashed working-tree changes]")
        return True

    stderr_text = result.stderr.decode(errors="replace") if result.stderr else ""
    print(f"[WARNING] git stash pop failed: {stderr_text.strip()}")

    # Recover gracefully: reset conflicted files to HEAD, then drop the stale stash.
    # The stash typically contains only the plan YAML with an outdated in_progress
    # status that the agent has since committed as completed.  Keeping the stash
    # around would block future pops and leave merge markers in the working tree.
    # git reset --merge must precede git checkout . to clear UU (unmerged) index state;
    # git checkout . alone cannot restore files in unresolved conflict status.
    print("[RECOVERY] Resetting working tree to HEAD and dropping stale stash...")
    subprocess.run(["git", "reset", "--merge"], capture_output=True)
    subprocess.run(["git", "checkout", "."], capture_output=True)
    subprocess.run(["git", "stash", "drop"], capture_output=True)
    print("[RECOVERY] Working tree restored to clean state")
    return False


# ─── Worktree Helpers ─────────────────────────────────────────────────────────


def get_worktree_path(plan_name: str, task_id: str) -> Path:
    """Get the path for a task's worktree."""
    safe_plan_name = plan_name.replace(" ", "-").lower()[:30]
    safe_task_id = task_id.replace(".", "-")
    return Path(WORKTREE_BASE_DIR) / f"{safe_plan_name}-{safe_task_id}"


def create_worktree(plan_name: str, task_id: str) -> Optional[Path]:
    """Create a git worktree for a task.

    Returns the worktree path if successful, None if failed.
    """
    worktree_path = get_worktree_path(plan_name, task_id)
    branch_name = f"parallel/{task_id.replace('.', '-')}"

    Path(WORKTREE_BASE_DIR).mkdir(parents=True, exist_ok=True)

    if worktree_path.exists():
        cleanup_worktree(worktree_path)

    # Delete stale branch if it exists (from previous failed run)
    subprocess.run(
        ["git", "branch", "-D", branch_name],
        capture_output=True,
        text=True,
        check=False
    )

    # Prune any stale worktree references
    subprocess.run(
        ["git", "worktree", "prune"],
        capture_output=True,
        text=True,
        check=False
    )

    try:
        # Create worktree with new branch from current HEAD
        subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
            capture_output=True,
            text=True,
            check=True
        )

        # Clear stale task-status.json inherited from main branch to prevent
        # the orchestrator from reading results from a previous plan's run
        stale_status = worktree_path / ".claude" / "plans" / "task-status.json"
        if stale_status.exists():
            stale_status.unlink(missing_ok=True)

        return worktree_path

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to create worktree: {e.stderr}")
        return None


def cleanup_worktree(worktree_path: Path) -> bool:
    """Remove a worktree and its branch.

    Returns True if cleanup was successful.
    """
    try:
        subprocess.run(
            ["git", "worktree", "remove", str(worktree_path), "--force"],
            capture_output=True,
            text=True,
            check=False
        )

        subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True,
            text=True,
            check=False
        )

        return True

    except Exception as e:
        print(f"[WARNING] Failed to cleanup worktree {worktree_path}: {e}")
        return False


def copy_worktree_artifacts(
    worktree_path: Path, task_id: str
) -> tuple[bool, str, list[str]]:
    """Copy changed files from a worktree into the main working directory.

    Instead of using git merge (which fails when multiple parallel branches all
    modify the YAML plan file), this function:
    1. Diffs the worktree branch against the fork point to find changed files
    2. Copies added/modified files from the worktree into main
    3. Removes deleted files from main
    4. Skips coordination files (.claude/plans/) that the orchestrator manages

    Returns (success, message, files_copied) tuple.
    """
    branch_name = f"parallel/{task_id.replace('.', '-')}"

    try:
        fork_result = subprocess.run(
            ["git", "merge-base", "HEAD", branch_name],
            capture_output=True, text=True, check=True
        )
        fork_point = fork_result.stdout.strip()

        diff_result = subprocess.run(
            ["git", "diff", "--name-status", fork_point, branch_name],
            capture_output=True, text=True, check=True
        )

        if not diff_result.stdout.strip():
            return (True, "No changes to copy", [])

        files_copied: list[str] = []
        files_deleted: list[str] = []
        files_skipped: list[str] = []

        for line in diff_result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            status = parts[0][0]  # A, M, D, R, C (first char)
            file_path = parts[-1]  # Last element handles renames

            if any(file_path.startswith(prefix) for prefix in _WORKTREE_SKIP_PREFIXES):
                files_skipped.append(file_path)
                continue

            if status in ("A", "M", "C"):
                src = worktree_path / file_path
                dst = Path(file_path)
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                    files_copied.append(file_path)

            elif status == "D":
                dst = Path(file_path)
                if dst.exists():
                    dst.unlink()
                    files_deleted.append(file_path)

            elif status == "R":
                if len(parts) >= 3:
                    old_path = parts[1]
                    new_path = parts[2]
                    src = worktree_path / new_path
                    if src.exists():
                        Path(new_path).parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(src), str(new_path))
                        files_copied.append(new_path)
                        old_dst = Path(old_path)
                        if old_dst.exists():
                            old_dst.unlink(missing_ok=True)
                            files_deleted.append(old_path)

        all_changes = files_copied + files_deleted
        summary_parts = []
        if files_copied:
            summary_parts.append(f"{len(files_copied)} copied")
        if files_deleted:
            summary_parts.append(f"{len(files_deleted)} deleted")
        if files_skipped:
            summary_parts.append(f"{len(files_skipped)} skipped")
        summary = ", ".join(summary_parts) or "no file changes"

        # Delete the branch after successful copy
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            capture_output=True, text=True, check=False
        )

        return (True, f"Copied from {branch_name}: {summary}", all_changes)

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr or e.stdout or str(e)
        return (False, f"Failed to copy artifacts: {error_msg}", [])


# ─── Commit Helpers ───────────────────────────────────────────────────────────


def git_commit_files(file_paths: list[str], message: str) -> bool:
    """Stage and commit a list of files with the given message.

    Returns True if the commit succeeded, False otherwise.
    """
    try:
        subprocess.run(
            ["git", "add"] + file_paths,
            capture_output=True,
            check=True
        )
        subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"[Warning: git commit failed: {e}]")
        return False
