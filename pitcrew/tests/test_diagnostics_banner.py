"""The startup banner - the one line that identifies a run after the fact.

It had no test at all, which is how it came to cost **71 ms of every launch**:
`platform.platform()` assembles its string from two separate WMI queries, and
nothing reads the result. `sys.getwindowsversion()` gives the same build
number in 0.49 ms.

What is pinned here is not the wording. It is that the banner still emits when
the expensive call is unavailable - because the banner runs under `pythonw`
with no console, and a banner that raised would take the whole launch with it
while leaving nothing behind to say why.
"""
from __future__ import annotations

import sys

import pytest

from pitcrew import diagnostics


def test_the_banner_says_which_python_and_which_machine(caplog):
    with caplog.at_level("INFO"):
        diagnostics.banner(pid=1, version="pitcrew test")
    said = "\n".join(record.getMessage() for record in caplog.records)
    assert "Pit Crew starting" in said
    assert sys.version.split()[0] in said
    assert sys.platform in said
    assert "pid: 1" in said


@pytest.mark.skipif(sys.platform != "win32", reason="the fast path is Windows")
def test_the_build_number_survives_the_cheap_path(caplog):
    """The marketing name and the service pack go; the build number is the
    part a crash investigation actually uses, and it must not."""
    with caplog.at_level("INFO"):
        diagnostics.banner(pid=1, version="pitcrew test")
    said = "\n".join(record.getMessage() for record in caplog.records)
    assert str(sys.getwindowsversion().build) in said


@pytest.mark.skipif(sys.platform != "win32", reason="the fast path is Windows")
def test_the_raw_version_tuple_is_there_too(caplog):
    """`getwindowsversion` reports the *manifested* version. Repackaged
    without a manifest it silently returns 6.2.9200 on a machine running 11 -
    a well-formed wrong answer in the one line identifying the machine.
    Printed next to its own tuple, that reads as the manifest talking."""
    with caplog.at_level("INFO"):
        diagnostics.banner(pid=1, version="pitcrew test")
    said = "\n".join(record.getMessage() for record in caplog.records)
    version = sys.getwindowsversion()
    assert f"({version.major}, {version.minor}, {version.build})" in said


def test_the_banner_survives_a_platform_call_that_raises(monkeypatch, caplog):
    """The regression guard. If someone reintroduces `platform.platform()`
    on the Windows path, this is what notices - and under `pythonw` a banner
    that raises leaves no trace at all."""
    def boom():
        raise OSError("WMI is not answering")

    monkeypatch.setattr("platform.platform", boom)
    with caplog.at_level("INFO"):
        diagnostics.banner(pid=1, version="pitcrew test")
    assert any("Pit Crew starting" in record.getMessage()
               for record in caplog.records)


@pytest.mark.skipif(sys.platform != "win32", reason="the fast path is Windows")
def test_the_banner_does_not_go_near_wmi(monkeypatch):
    """The saving itself, asserted where it is unambiguous. `platform.uname`
    is what pulls in `_wmi`, and it is 71 of the banner's 73 ms."""
    monkeypatch.setattr("platform.uname",
                        lambda: pytest.fail("the banner asked WMI again"))
    diagnostics.banner(pid=1, version="pitcrew test")
