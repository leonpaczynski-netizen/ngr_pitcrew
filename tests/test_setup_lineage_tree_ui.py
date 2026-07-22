"""Tests for the vertical setup lineage tree UI component (F2.4).

(Distinct from tests/test_setup_lineage.py, which covers the domain
strategy/setup_lineage module.)
"""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components.setup_lineage import SetupLineageTree, LineageNode


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _nodes():
    return [
        LineageNode("n3", "Quali v3", outcome="improved", is_current=True,
                    summary="Rear ARB 5->4", discipline="qualifying"),
        LineageNode("n2", "Quali v2", outcome="worse",
                    summary="Softer front springs - lost front end"),
        LineageNode("n1", "Base", outcome="", summary="Baseline build"),
    ]


class TestLineageTree:
    def test_renders_all_nodes(self, qapp):
        t = SetupLineageTree()
        t.set_nodes(_nodes())
        assert t._empty.isHidden() is True
        count = sum(1 for i in range(t._body.count()) if t._body.itemAt(i).widget())
        assert count == 3

    def test_empty_shows_placeholder(self, qapp):
        t = SetupLineageTree()
        t.set_nodes(())
        assert t._empty.isHidden() is False

    def test_revert_emits_node_id(self, qapp):
        t = SetupLineageTree()
        t.set_nodes(_nodes())
        seen = []
        t.revert_requested.connect(lambda nid: seen.append(nid))
        t.revert_requested.emit("n2")
        assert seen == ["n2"]

    def test_rerender_clears(self, qapp):
        t = SetupLineageTree()
        t.set_nodes(_nodes())
        t.set_nodes(_nodes()[:1])
        count = sum(1 for i in range(t._body.count()) if t._body.itemAt(i).widget())
        assert count == 1

    def test_defensive_against_garbage(self, qapp):
        t = SetupLineageTree()
        t.set_nodes(["not a node", None])
        assert t._empty.isHidden() is False


class TestWorkspaceLineageIntegration:
    def test_workspace_populates_and_forwards_revert(self, qapp):
        from ui.components.setup_workspace import SetupWorkspace
        from ui.setup_recommendation_vm import build_recommendation_vm
        w = SetupWorkspace()
        seen = []
        w.revert_requested.connect(lambda nid: seen.append(nid))
        w.set_recommendation(build_recommendation_vm({}), lineage_nodes=_nodes())
        w._lineage.revert_requested.emit("n2")
        assert seen == ["n2"]
