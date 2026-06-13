"""gitdiff: changed-file extraction, watch-glob filtering, change kinds."""

from __future__ import annotations

from specguard.gitdiff import diff_from_contents, watched_changes

WATCH = ["README.md", "*.kilo", ".specguard/**"]


def test_watch_filter_skips_non_watched_files(git_repo):
    git_repo.write("README.md", "v1\n")
    git_repo.write("src/main.py", "print(1)\n")
    base = git_repo.commit_all("base")
    git_repo.write("README.md", "v2\n")
    git_repo.write("src/main.py", "print(2)\n")
    head = git_repo.commit_all("head")
    changes = watched_changes(git_repo.root, base, head, WATCH)
    assert [c.path for c in changes] == ["README.md"]


def test_modified_file_carries_diff_and_contents(git_repo):
    git_repo.write("README.md", "hello wrld\n")
    base = git_repo.commit_all("base")
    git_repo.write("README.md", "hello world\n")
    head = git_repo.commit_all("head")
    (change,) = watched_changes(git_repo.root, base, head, WATCH)
    assert change.change == "modified"
    assert change.old_content == "hello wrld\n"
    assert change.new_content == "hello world\n"
    assert "-hello wrld" in change.diff
    assert "+hello world" in change.diff


def test_added_and_deleted_files(git_repo):
    git_repo.write("README.md", "keep\n")
    git_repo.write(".specguard/roles.yml", "roles: {}\n")
    base = git_repo.commit_all("base")
    git_repo.write("notes.kilo", "new file\n")
    git_repo.delete(".specguard/roles.yml")
    head = git_repo.commit_all("head")
    changes = {c.path: c for c in watched_changes(git_repo.root, base, head, WATCH)}
    assert changes["notes.kilo"].change == "added"
    assert changes["notes.kilo"].old_content == ""
    assert changes[".specguard/roles.yml"].change == "deleted"
    assert changes[".specguard/roles.yml"].new_content == ""


def test_rename_governs_new_path(git_repo):
    git_repo.write("OLD.kilo", "same content\n" * 10)
    base = git_repo.commit_all("base")
    git_repo.git("mv", "OLD.kilo", "NEW.kilo")
    head = git_repo.commit_all("head")
    changes = watched_changes(git_repo.root, base, head, WATCH)
    assert [c.path for c in changes] == ["NEW.kilo"]


def test_merge_base_diff_ignores_changes_on_base_branch(git_repo):
    # base...head must reflect only the PR's commits, not what landed on main.
    git_repo.write("README.md", "original\n")
    base = git_repo.commit_all("base")
    git_repo.git("checkout", "-q", "-b", "feature")
    git_repo.write("notes.kilo", "feature work\n")
    head = git_repo.commit_all("feature commit")
    git_repo.git("checkout", "-q", "main")
    git_repo.write("README.md", "main moved on\n")
    git_repo.commit_all("main advance")
    changes = watched_changes(git_repo.root, "main", head, WATCH)
    assert [c.path for c in changes] == ["notes.kilo"]
    _ = base


def test_diff_from_contents_change_kinds():
    assert diff_from_contents("f.md", "", "x\n").change == "added"
    assert diff_from_contents("f.md", "x\n", "").change == "deleted"
    assert diff_from_contents("f.md", "x\n", "y\n").change == "modified"
