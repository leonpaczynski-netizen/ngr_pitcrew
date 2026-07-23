"""Headless application services — the layer between the domain and any UI.

These own no widgets and import no Qt. A surface calls a service; a service calls the
domain. This is what lets the new shell run without the classic window.
"""
