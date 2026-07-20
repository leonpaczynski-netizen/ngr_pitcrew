"""Engineering Brain Program 2 Phase 12 — Qt-free knowledge view-model tests."""
import pytest

from ui import engineering_knowledge_vm as vm


def test_not_empty_and_groups_in_ui_order():
    assert not vm.is_empty(None)
    titles = vm.group_titles()
    keys = [k for k, _ in titles]
    # spec grouping present and suspension leads
    assert keys[0] == "suspension"
    for req in ("suspension", "differential", "aero", "tyres", "brakes",
                "transmission", "weight_transfer"):
        assert req in keys


def test_component_rows_shape():
    rows = vm.component_rows(None, "differential")
    assert rows and all(len(r) == len(vm.COMPONENT_COLUMNS) for r in rows)
    assert any("Lsd" in r[0] for r in rows)


def test_load_transfer_rows():
    rows = vm.load_transfer_rows()
    assert len(rows) == 7 and all(len(r) == len(vm.LOAD_COLUMNS) for r in rows)


def test_handling_phase_rows():
    rows = vm.handling_phase_rows()
    assert len(rows) == 8 and all(len(r) == len(vm.PHASE_COLUMNS) for r in rows)


def test_interaction_rows():
    rows = vm.interaction_rows()
    assert rows and all(len(r) == len(vm.INTERACTION_COLUMNS) for r in rows)


def test_lsd_and_aero_rows():
    assert len(vm.lsd_rows()) == 3
    assert len(vm.aero_rows()) == 5


def test_falls_back_to_static_knowledge():
    # the VM always loads the static, deterministic knowledge base — a not-ok input
    # simply triggers the fallback, so the panel is never empty in normal operation.
    assert not vm.is_empty({"ok": False})
    assert not vm.is_empty(None)
    assert vm.build({"ok": False}).get("ok")
