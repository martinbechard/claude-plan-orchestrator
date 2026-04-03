# tests/langgraph/shared/test_git.py
# Unit tests for the shared git module.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md

"""Unit tests for langgraph_pipeline.shared.git."""

import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from langgraph_pipeline.shared.git import (
    ORCHESTRATOR_STASH_MESSAGE,
    STASH_EXCLUDE_PLANS_PATHSPEC,
    WORKTREE_BASE_DIR,
    _GIT_WORKTREE_LOCK,
    _WORKTREE_CREATE_MAX_ATTEMPTS,
    _WORKTREE_SKIP_PREFIXES,
    _file_exists_in_ref,
    cleanup_worktree,
    copy_worktree_artifacts,
    create_worktree,
    get_worktree_path,
    git_commit_files,
    git_stash_pop,
    git_stash_working_changes,
)


# ─── Constants ────────────────────────────────────────────────────────────────


class TestConstants:
    def test_stash_message_is_string(self):
        assert isinstance(ORCHESTRATOR_STASH_MESSAGE, str)
        assert ORCHESTRATOR_STASH_MESSAGE  # non-empty

    def test_stash_exclude_pathspec_excludes_plans(self):
        assert "tmp/plans/" in STASH_EXCLUDE_PLANS_PATHSPEC

    def test_worktree_base_dir_is_string(self):
        assert isinstance(WORKTREE_BASE_DIR, str)
        assert WORKTREE_BASE_DIR  # non-empty

    def test_skip_prefixes_contains_plans_dir(self):
        assert any("tmp/plans/" in p for p in _WORKTREE_SKIP_PREFIXES)

    def test_skip_prefixes_contains_subagent_status(self):
        assert any("subagent-status" in p for p in _WORKTREE_SKIP_PREFIXES)

    def test_skip_prefixes_contains_agent_claims(self):
        assert any("agent-claims" in p for p in _WORKTREE_SKIP_PREFIXES)


# ─── _file_exists_in_ref ──────────────────────────────────────────────────────


class TestFileExistsInRef:
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_returns_true_when_cat_file_exits_zero(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert _file_exists_in_ref("HEAD", "some/file.py") is True

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_returns_false_when_cat_file_exits_nonzero(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert _file_exists_in_ref("abc123", "deleted/file.py") is False

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_uses_cat_file_dash_e_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        _file_exists_in_ref("HEAD", "src/foo.py")
        cmd = mock_run.call_args[0][0]
        assert "cat-file" in cmd
        assert "-e" in cmd

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_formats_ref_colon_path(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        _file_exists_in_ref("abc123", "docs/backlog/16.md")
        cmd = mock_run.call_args[0][0]
        assert "abc123:docs/backlog/16.md" in cmd


# ─── git_stash_working_changes ────────────────────────────────────────────────


class TestGitStashWorkingChanges:
    def _make_run(self, diff_rc=0, cached_rc=0, untracked_output=b""):
        """Build a side_effect list for subprocess.run covering stash check calls."""
        results = [
            MagicMock(returncode=diff_rc),
            MagicMock(returncode=cached_rc),
            MagicMock(returncode=0, stdout=untracked_output),
        ]
        return results

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_returns_false_when_tree_is_clean(self, mock_run):
        mock_run.side_effect = self._make_run(diff_rc=0, cached_rc=0, untracked_output=b"")
        result = git_stash_working_changes()
        assert result is False

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_returns_true_when_stash_succeeds(self, mock_run):
        check_results = self._make_run(diff_rc=1)  # dirty tree
        stash_result = MagicMock(returncode=0)
        mock_run.side_effect = check_results + [stash_result]
        result = git_stash_working_changes()
        assert result is True

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_returns_false_when_stash_fails(self, mock_run):
        check_results = self._make_run(diff_rc=1)
        stash_result = MagicMock(returncode=1)
        mock_run.side_effect = check_results + [stash_result]
        result = git_stash_working_changes()
        assert result is False

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_stash_command_includes_message(self, mock_run):
        check_results = self._make_run(diff_rc=1)
        stash_result = MagicMock(returncode=0)
        mock_run.side_effect = check_results + [stash_result]
        git_stash_working_changes()
        stash_call_args = mock_run.call_args_list[3][0][0]
        assert ORCHESTRATOR_STASH_MESSAGE in stash_call_args

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_stash_command_excludes_plans_dir(self, mock_run):
        check_results = self._make_run(diff_rc=1)
        stash_result = MagicMock(returncode=0)
        mock_run.side_effect = check_results + [stash_result]
        git_stash_working_changes()
        stash_call_args = mock_run.call_args_list[3][0][0]
        assert STASH_EXCLUDE_PLANS_PATHSPEC in stash_call_args

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_dirty_untracked_files_triggers_stash(self, mock_run):
        check_results = self._make_run(
            diff_rc=0, cached_rc=0, untracked_output=b"somefile.txt\n"
        )
        stash_result = MagicMock(returncode=0)
        mock_run.side_effect = check_results + [stash_result]
        result = git_stash_working_changes()
        assert result is True


# ─── git_stash_pop ────────────────────────────────────────────────────────────


class TestGitStashPop:
    @patch("langgraph_pipeline.shared.git.os.path.exists", return_value=False)
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_returns_true_on_success(self, mock_run, mock_exists):
        mock_run.return_value = MagicMock(returncode=0)
        result = git_stash_pop()
        assert result is True

    @patch("langgraph_pipeline.shared.git.os.path.exists", return_value=False)
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_returns_false_on_failure(self, mock_run, mock_exists):
        pop_fail = MagicMock(returncode=1, stderr=b"conflict")
        recovery = MagicMock(returncode=0)
        mock_run.side_effect = [pop_fail, recovery, recovery, recovery]
        result = git_stash_pop()
        assert result is False

    @patch("langgraph_pipeline.shared.git.os.path.exists", return_value=True)
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_checks_out_status_file_before_pop(self, mock_run, mock_exists):
        mock_run.return_value = MagicMock(returncode=0)
        git_stash_pop()
        first_call = mock_run.call_args_list[0][0][0]
        assert "checkout" in first_call

    @patch("langgraph_pipeline.shared.git.os.path.exists", return_value=False)
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_recovery_resets_and_drops_stash_on_failure(self, mock_run, mock_exists):
        pop_fail = MagicMock(returncode=1, stderr=b"conflict")
        recovery = MagicMock(returncode=0)
        mock_run.side_effect = [pop_fail, recovery, recovery, recovery]
        git_stash_pop()
        all_cmds = [c[0][0] for c in mock_run.call_args_list]
        assert any("reset" in cmd for cmd in all_cmds)
        assert any("drop" in cmd for cmd in all_cmds)


# ─── get_worktree_path ────────────────────────────────────────────────────────


class TestGetWorktreePath:
    def test_returns_path_under_worktree_base_dir(self):
        result = get_worktree_path("My Plan", "1.2")
        assert str(result).startswith(WORKTREE_BASE_DIR)

    def test_spaces_replaced_with_dashes(self):
        result = get_worktree_path("my plan name", "1.2")
        assert " " not in str(result)

    def test_dots_replaced_with_dashes_in_task_id(self):
        result = get_worktree_path("plan", "3.1")
        assert "3-1" in str(result)

    def test_plan_name_lowercased(self):
        result = get_worktree_path("MY PLAN", "1.1")
        assert "my-plan" in str(result)

    def test_plan_name_truncated_to_30_chars(self):
        long_name = "a" * 50
        result = get_worktree_path(long_name, "1.1")
        # The plan part should be at most 30 chars
        stem = result.name
        plan_part = stem.rsplit("-", 2)[0]
        assert len(plan_part) <= 30

    def test_returns_path_object(self):
        result = get_worktree_path("plan", "1.1")
        assert isinstance(result, Path)


# ─── create_worktree ─────────────────────────────────────────────────────────


class TestCreateWorktree:
    @patch("langgraph_pipeline.shared.git._cleanup_worktree_unlocked")
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    @patch("langgraph_pipeline.shared.git.Path.mkdir")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=False)
    def test_returns_path_on_success(self, mock_exists, mock_mkdir, mock_run, mock_cleanup):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = create_worktree("my-plan", "1.1")
        assert result is not None
        assert isinstance(result, Path)

    @patch("langgraph_pipeline.shared.git.time.sleep")
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    @patch("langgraph_pipeline.shared.git.Path.mkdir")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=False)
    def test_returns_none_after_all_retries_exhausted(self, mock_exists, mock_mkdir, mock_run, mock_sleep):
        # branch -D and prune succeed, all worktree add attempts fail
        add_error = subprocess.CalledProcessError(1, "git", stderr="index.lock")
        mock_run.side_effect = [
            MagicMock(returncode=0),  # branch -D
            MagicMock(returncode=0),  # worktree prune
        ] + [add_error] * _WORKTREE_CREATE_MAX_ATTEMPTS
        result = create_worktree("my-plan", "1.1")
        assert result is None
        # Retries should sleep between attempts (max_attempts - 1 sleeps)
        assert mock_sleep.call_count == _WORKTREE_CREATE_MAX_ATTEMPTS - 1

    @patch("langgraph_pipeline.shared.git.time.sleep")
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    @patch("langgraph_pipeline.shared.git.Path.mkdir")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=False)
    def test_succeeds_on_retry_after_transient_failure(self, mock_exists, mock_mkdir, mock_run, mock_sleep):
        add_error = subprocess.CalledProcessError(1, "git", stderr="index.lock")
        mock_run.side_effect = [
            MagicMock(returncode=0),  # branch -D
            MagicMock(returncode=0),  # worktree prune
            add_error,               # first add attempt fails
            MagicMock(returncode=0, stdout="", stderr=""),  # second add succeeds
        ]
        result = create_worktree("my-plan", "1.1")
        assert result is not None
        assert mock_sleep.call_count == 1

    @patch("langgraph_pipeline.shared.git._cleanup_worktree_unlocked")
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    @patch("langgraph_pipeline.shared.git.Path.mkdir")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=True)
    def test_cleans_up_existing_worktree(self, mock_exists, mock_mkdir, mock_run, mock_cleanup):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        create_worktree("my-plan", "1.1")
        mock_cleanup.assert_called_once()

    @patch("langgraph_pipeline.shared.git._cleanup_worktree_unlocked")
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    @patch("langgraph_pipeline.shared.git.Path.mkdir")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=False)
    def test_branch_name_uses_parallel_prefix(self, mock_exists, mock_mkdir, mock_run, mock_cleanup):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        create_worktree("plan", "2.3")
        add_call = next(
            c for c in mock_run.call_args_list if "worktree" in c[0][0] and "add" in c[0][0]
        )
        assert "parallel/2-3" in add_call[0][0]

    def test_lock_is_a_threading_lock(self):
        """Verify the worktree lock exists and is a proper threading.Lock."""
        import threading
        assert isinstance(_GIT_WORKTREE_LOCK, type(threading.Lock()))


# ─── cleanup_worktree ─────────────────────────────────────────────────────────


class TestCleanupWorktree:
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = cleanup_worktree(Path(".worktrees/plan-1-1"))
        assert result is True

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_calls_worktree_remove_and_prune(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        cleanup_worktree(Path(".worktrees/plan-1-1"))
        cmds = [c[0][0] for c in mock_run.call_args_list]
        assert any("remove" in cmd for cmd in cmds)
        assert any("prune" in cmd for cmd in cmds)

    @patch("langgraph_pipeline.shared.git.subprocess.run", side_effect=Exception("err"))
    def test_returns_false_on_exception(self, mock_run):
        result = cleanup_worktree(Path(".worktrees/plan-1-1"))
        assert result is False


# ─── copy_worktree_artifacts ──────────────────────────────────────────────────


class TestCopyWorktreeArtifacts:
    def _make_run_results(self, fork="abc123", diff_output="", extra=None):
        """Build side_effect list for subprocess.run calls in copy_worktree_artifacts.

        extra: additional MagicMock results injected between diff and branch_del,
               used for cat-file existence checks in the deletion guard.
        """
        fork_result = MagicMock(returncode=0, stdout=fork, stderr="")
        diff_result = MagicMock(returncode=0, stdout=diff_output, stderr="")
        branch_del = MagicMock(returncode=0)
        middle = extra or []
        return [fork_result, diff_result] + middle + [branch_del]

    def _cat_file(self, exists: bool) -> MagicMock:
        """Build a mock cat-file subprocess result."""
        return MagicMock(returncode=0 if exists else 1)

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_returns_true_with_no_changes(self, mock_run):
        mock_run.side_effect = self._make_run_results(diff_output="")
        success, msg, files = copy_worktree_artifacts(Path(".worktrees/plan-1-1"), "1.1")
        assert success is True
        assert files == []

    @patch("langgraph_pipeline.shared.git.shutil.copy2")
    @patch("langgraph_pipeline.shared.git.Path.mkdir")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=True)
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_copies_added_files(self, mock_run, mock_exists, mock_mkdir, mock_copy):
        # A-status: file not at fork_point (cat-file returns 1) → short-circuit → copy
        diff_output = "A\tsome/file.py\n"
        extra = [self._cat_file(exists=False)]  # fork check: not at fork → new file
        mock_run.side_effect = self._make_run_results(diff_output=diff_output, extra=extra)
        success, msg, files = copy_worktree_artifacts(Path(".worktrees/plan"), "1.1")
        assert success is True
        assert "some/file.py" in files

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_skips_plans_dir_files(self, mock_run):
        # Prefix-skipped files never reach the cat-file guard
        diff_output = "M\ttmp/plans/02-extract.yaml\n"
        mock_run.side_effect = self._make_run_results(diff_output=diff_output)
        success, msg, files = copy_worktree_artifacts(Path(".worktrees/plan"), "1.1")
        assert success is True
        assert "tmp/plans/02-extract.yaml" not in files

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_skips_subagent_status_files(self, mock_run):
        # Prefix-skipped files never reach the cat-file guard
        diff_output = "A\t.claude/subagent-status/agent.json\n"
        mock_run.side_effect = self._make_run_results(diff_output=diff_output)
        success, msg, files = copy_worktree_artifacts(Path(".worktrees/plan"), "1.1")
        assert ".claude/subagent-status/agent.json" not in files

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_returns_false_on_subprocess_error(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "git", stderr="error")
        success, msg, files = copy_worktree_artifacts(Path(".worktrees/plan"), "1.1")
        assert success is False

    @patch("langgraph_pipeline.shared.git.Path.unlink")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=True)
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_deletes_removed_files(self, mock_run, mock_exists, mock_unlink):
        # D-status files bypass the cat-file guard entirely
        diff_output = "D\tsome/old_file.py\n"
        mock_run.side_effect = self._make_run_results(diff_output=diff_output)
        success, msg, files = copy_worktree_artifacts(Path(".worktrees/plan"), "1.1")
        assert success is True
        assert "some/old_file.py" in files

    @patch("langgraph_pipeline.shared.git.shutil.copy2")
    @patch("langgraph_pipeline.shared.git.Path.mkdir")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=True)
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_handles_modified_files(self, mock_run, mock_exists, mock_mkdir, mock_copy):
        # M-status: file existed at fork (check 1=True) and still in HEAD (check 2=True) → copy
        diff_output = "M\tsrc/module.py\n"
        extra = [self._cat_file(exists=True), self._cat_file(exists=True)]
        mock_run.side_effect = self._make_run_results(diff_output=diff_output, extra=extra)
        success, msg, files = copy_worktree_artifacts(Path(".worktrees/plan"), "1.1")
        assert "src/module.py" in files

    @patch("langgraph_pipeline.shared.git.shutil.copy2")
    @patch("langgraph_pipeline.shared.git.Path.mkdir")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=True)
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_handles_renamed_files(self, mock_run, mock_exists, mock_mkdir, mock_copy):
        # R-status new_path: not at fork_point (new path in rename) → short-circuit → copy
        diff_output = "R100\told/path.py\tnew/path.py\n"
        extra = [self._cat_file(exists=False)]  # new_path not at fork → copy normally
        mock_run.side_effect = self._make_run_results(diff_output=diff_output, extra=extra)
        success, msg, files = copy_worktree_artifacts(Path(".worktrees/plan"), "1.1")
        assert "new/path.py" in files

    @patch("langgraph_pipeline.shared.git.shutil.copy2")
    @patch("langgraph_pipeline.shared.git.Path.mkdir")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=True)
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_deletes_branch_on_success(self, mock_run, mock_exists, mock_mkdir, mock_copy):
        # A-status: file not at fork → short-circuit cat-file → copy
        diff_output = "A\tsome/file.py\n"
        extra = [self._cat_file(exists=False)]
        mock_run.side_effect = self._make_run_results(diff_output=diff_output, extra=extra)
        copy_worktree_artifacts(Path(".worktrees/plan"), "2.3")
        delete_call = mock_run.call_args_list[-1][0][0]
        assert "branch" in delete_call
        assert "-D" in delete_call
        assert "parallel/2-3" in delete_call

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_summary_message_describes_changes(self, mock_run):
        # A-status: file not at fork → short-circuit → copy
        diff_output = "A\tsome/file.py\n"
        fork_result = MagicMock(returncode=0, stdout="abc", stderr="")
        diff_result = MagicMock(returncode=0, stdout=diff_output, stderr="")
        cat_file_fork = MagicMock(returncode=1)  # not at fork → copy
        branch_del = MagicMock(returncode=0)
        exists_patch = patch(
            "langgraph_pipeline.shared.git.Path.exists", return_value=True
        )
        mkdir_patch = patch("langgraph_pipeline.shared.git.Path.mkdir")
        copy_patch = patch("langgraph_pipeline.shared.git.shutil.copy2")
        mock_run.side_effect = [fork_result, diff_result, cat_file_fork, branch_del]
        with exists_patch, mkdir_patch, copy_patch:
            _, msg, _ = copy_worktree_artifacts(Path(".worktrees/plan"), "1.1")
        assert "copied" in msg

    @patch("langgraph_pipeline.shared.git.shutil.copy2")
    @patch("langgraph_pipeline.shared.git.Path.mkdir")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=True)
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_skips_file_deleted_from_main_after_fork(
        self, mock_run, mock_exists, mock_mkdir, mock_copy
    ):
        # M-status: file existed at fork (check 1=True) but deleted from main HEAD (check 2=False) → skip
        diff_output = "M\tdocs/feature-backlog/16.md\n"
        extra = [self._cat_file(exists=True), self._cat_file(exists=False)]
        mock_run.side_effect = self._make_run_results(diff_output=diff_output, extra=extra)
        success, msg, files = copy_worktree_artifacts(Path(".worktrees/plan"), "1.1")
        assert success is True
        assert "docs/feature-backlog/16.md" not in files
        mock_copy.assert_not_called()

    @patch("langgraph_pipeline.shared.git.shutil.copy2")
    @patch("langgraph_pipeline.shared.git.Path.mkdir")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=True)
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_skipped_deletion_guard_files_appear_in_summary(
        self, mock_run, mock_exists, mock_mkdir, mock_copy
    ):
        # Skipped files (deleted in main after fork) are reflected in the summary message
        diff_output = "M\tdocs/feature-backlog/16.md\n"
        extra = [self._cat_file(exists=True), self._cat_file(exists=False)]
        mock_run.side_effect = self._make_run_results(diff_output=diff_output, extra=extra)
        _, msg, _ = copy_worktree_artifacts(Path(".worktrees/plan"), "1.1")
        assert "skipped" in msg

    @patch("langgraph_pipeline.shared.git.shutil.copy2")
    @patch("langgraph_pipeline.shared.git.Path.mkdir")
    @patch("langgraph_pipeline.shared.git.Path.exists", return_value=True)
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_genuinely_new_added_file_not_affected_by_deletion_guard(
        self, mock_run, mock_exists, mock_mkdir, mock_copy
    ):
        # A-status for a file not at fork_point → cat-file returns 1 → short-circuit → copy without skip
        diff_output = "A\tnew/feature.py\n"
        extra = [self._cat_file(exists=False)]  # not at fork → genuinely new
        mock_run.side_effect = self._make_run_results(diff_output=diff_output, extra=extra)
        success, msg, files = copy_worktree_artifacts(Path(".worktrees/plan"), "1.1")
        assert success is True
        assert "new/feature.py" in files


# ─── git_commit_files ─────────────────────────────────────────────────────────


class TestGitCommitFiles:
    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = git_commit_files(["file.py"], "test commit")
        assert result is True

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_calls_git_add_then_commit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        git_commit_files(["a.py", "b.py"], "msg")
        calls = mock_run.call_args_list
        assert "add" in calls[0][0][0]
        assert "commit" in calls[1][0][0]

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_passes_message_to_commit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        git_commit_files(["a.py"], "my message")
        commit_call = mock_run.call_args_list[1][0][0]
        assert "my message" in commit_call

    @patch(
        "langgraph_pipeline.shared.git.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "git"),
    )
    def test_returns_false_on_failure(self, mock_run):
        result = git_commit_files(["a.py"], "msg")
        assert result is False

    @patch("langgraph_pipeline.shared.git.subprocess.run")
    def test_passes_all_files_to_git_add(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        git_commit_files(["x.py", "y.py", "z.py"], "msg")
        add_call = mock_run.call_args_list[0][0][0]
        assert "x.py" in add_call
        assert "y.py" in add_call
        assert "z.py" in add_call
