"""Section-level locking: anchor location, region splitting, engine integration."""

from __future__ import annotations

import pytest

from conftest import FakeAdapter, make_classification
from specguard.config import ConfigError, parse_regions
from specguard.engine import evaluate_pr
from specguard.gitdiff import diff_from_contents
from specguard.models import Config, RegionsConfig
from specguard.regions import RegionAnchorError, split_into_regions

OLD = """# Architecture

## Goal
Build a thing.

## Out of Scope
We will not build SaaS.

## FAQ
Anything goes here.
"""


def modified(old: str, new: str, path: str = "ARCHITECTURE.md"):
    cf = diff_from_contents(path, old, new)
    cf.change = "modified"
    return cf


class TestSplitIntoRegions:
    def test_change_outside_region_has_no_region_verdicts(self):
        new = OLD.replace("Anything goes here.", "Anything goes here. Ponies too.")
        regions, outside = split_into_regions(modified(OLD, new), ["Out of Scope"])
        assert regions == []
        assert outside is True

    def test_change_inside_region_produces_one_region_diff(self):
        new = OLD.replace("We will not build SaaS.", "We will not build SaaS. Maybe?")
        regions, outside = split_into_regions(modified(OLD, new), ["Out of Scope"])
        assert len(regions) == 1
        assert regions[0].path == "ARCHITECTURE.md#Out of Scope"
        assert "Maybe?" in regions[0].new_content
        assert outside is False

    def test_unchanged_region_yields_no_region_diff(self):
        new = OLD.replace("Anything goes here.", "Something else entirely.")
        regions, outside = split_into_regions(modified(OLD, new), ["Out of Scope"])
        assert regions == []  # Out of Scope itself didn't change
        assert outside is True

    def test_multiple_anchors_each_evaluated_independently(self):
        new = OLD.replace("Build a thing.", "Build a thing. And more.").replace(
            "We will not build SaaS.", "We will not build SaaS. Ever."
        )
        regions, outside = split_into_regions(modified(OLD, new), ["Goal", "Out of Scope"])
        assert {r.path for r in regions} == {
            "ARCHITECTURE.md#Goal",
            "ARCHITECTURE.md#Out of Scope",
        }
        assert outside is False

    def test_anchor_missing_in_old_raises(self):
        cf = modified(OLD, OLD)
        with pytest.raises(RegionAnchorError, match="could not be located"):
            split_into_regions(cf, ["Nonexistent Heading"])

    def test_anchor_removed_in_new_raises(self):
        new = OLD.replace("## Out of Scope\nWe will not build SaaS.\n\n", "")
        with pytest.raises(RegionAnchorError, match="was removed"):
            split_into_regions(modified(OLD, new), ["Out of Scope"])

    def test_subsection_stays_inside_parent_region(self):
        old = "# Doc\n\n## Out of Scope\nIntro.\n\n### Details\nMore.\n\n## FAQ\nQ.\n"
        new = old.replace("More.", "More. Extra.")
        regions, outside = split_into_regions(modified(old, new, "DOC.md"), ["Out of Scope"])
        assert len(regions) == 1
        assert "Extra." in regions[0].new_content
        assert outside is False


class TestParseRegions:
    def test_absent_is_none(self):
        assert parse_regions(None) is None

    def test_valid_yaml_parses(self):
        cfg = parse_regions('files:\n  "ARCHITECTURE.md": ["Goal", "Out of Scope"]\n')
        assert cfg == RegionsConfig(files={"ARCHITECTURE.md": ["Goal", "Out of Scope"]})

    def test_malformed_yaml_raises(self):
        with pytest.raises(ConfigError, match="invalid YAML"):
            parse_regions("files: [unclosed\n")


class TestEngineIntegration:
    def lock(self):
        from specguard.models import ScopeLock

        return ScopeLock(goal="A docs tool", scope_in=[], scope_out=["SaaS pricing"])

    def pr(self):
        from specguard.models import PRContext

        return PRContext(
            pr_number=1, base_sha="a", head_sha="b", author_login="dev",
            is_fork=False, repo="acme/widgets",
        )

    def test_change_outside_region_passes_without_classifier_call(self):
        new = OLD.replace("Anything goes here.", "Anything goes here. Ponies too.")
        changed = [modified(OLD, new)]
        regions_config = RegionsConfig(files={"ARCHITECTURE.md": ["Out of Scope"]})
        adapter = FakeAdapter()
        verdicts = evaluate_pr(
            changed, self.lock(), Config(), None, self.pr(), adapter,
            lambda: [], regions_config=regions_config,
        )
        assert len(verdicts) == 1
        assert verdicts[0].outcome == "PASS"
        assert verdicts[0].reason == "region_ungoverned"
        assert verdicts[0].classification is None
        assert adapter.call_count == 0

    def test_change_inside_region_is_classified(self):
        new = OLD.replace(
            "We will not build SaaS.", "We will not build SaaS pricing tiers."
        )
        changed = [modified(OLD, new)]
        regions_config = RegionsConfig(files={"ARCHITECTURE.md": ["Out of Scope"]})
        adapter = FakeAdapter(
            responses={
                "ARCHITECTURE.md#Out of Scope": make_classification(
                    "SCOPE_CHANGE", 0.9, "HIGH", ["SaaS pricing"], "mentions pricing"
                )
            }
        )
        verdicts = evaluate_pr(
            changed, self.lock(), Config(), None, self.pr(), adapter,
            lambda: [], regions_config=regions_config,
        )
        assert len(verdicts) == 1
        assert verdicts[0].file == "ARCHITECTURE.md#Out of Scope"
        assert verdicts[0].outcome == "WARN"  # solo mode (no roles_config)
        assert adapter.call_count == 1

    def test_role_lookup_uses_original_path_not_region_path(self):
        """A scope_changes rule written against the whole file must still match
        a region sub-verdict — roles.yml authors don't know about #anchors."""
        from specguard.models import RolesConfig

        roles = RolesConfig.model_validate(
            {
                "roles": {"architect": ["alice"]},
                "rules": {"ARCHITECTURE.md": {"scope_changes": {"approve": "architect"}}},
            }
        )
        new = OLD.replace(
            "We will not build SaaS.", "We will not build SaaS pricing tiers."
        )
        changed = [modified(OLD, new)]
        regions_config = RegionsConfig(files={"ARCHITECTURE.md": ["Out of Scope"]})
        adapter = FakeAdapter(
            responses={
                "ARCHITECTURE.md#Out of Scope": make_classification(
                    "SCOPE_CHANGE", 0.95, "HIGH", ["SaaS pricing"], "pricing"
                )
            }
        )
        verdicts = evaluate_pr(
            changed, self.lock(), Config(), roles, self.pr(), adapter, lambda: [],
            regions_config=regions_config,
        )
        assert verdicts[0].outcome == "BLOCK"
        assert verdicts[0].required_approver_roles == ["architect"]

    def test_added_file_with_region_rule_governed_as_whole_file(self):
        # D1: an added file has no prior anchor to defend — region rules don't
        # apply; governance falls back to whole-file (unchanged) behavior.
        cf = diff_from_contents("ARCHITECTURE.md", "", OLD)
        regions_config = RegionsConfig(files={"ARCHITECTURE.md": ["Out of Scope"]})
        adapter = FakeAdapter(
            responses={"ARCHITECTURE.md": make_classification("ADDITIVE", 0.9)}
        )
        verdicts = evaluate_pr(
            [cf], self.lock(), Config(), None, self.pr(), adapter, lambda: [],
            regions_config=regions_config,
        )
        assert len(verdicts) == 1
        assert verdicts[0].file == "ARCHITECTURE.md"
        assert adapter.call_count == 1

    def test_no_regions_config_is_whole_file_unchanged(self):
        new = OLD.replace("Anything goes here.", "Anything else.")
        adapter = FakeAdapter(
            responses={"ARCHITECTURE.md": make_classification("ADDITIVE", 0.9)}
        )
        verdicts = evaluate_pr(
            [modified(OLD, new)], self.lock(), Config(), None, self.pr(), adapter,
            lambda: [],
        )
        assert len(verdicts) == 1
        assert verdicts[0].file == "ARCHITECTURE.md"

    def test_unresolvable_anchor_propagates_as_config_error(self):
        new = OLD.replace("## Out of Scope", "## Non-Goals")
        regions_config = RegionsConfig(files={"ARCHITECTURE.md": ["Out of Scope"]})
        with pytest.raises(ConfigError):
            evaluate_pr(
                [modified(OLD, new)], self.lock(), Config(), None, self.pr(),
                FakeAdapter(), lambda: [], regions_config=regions_config,
            )
