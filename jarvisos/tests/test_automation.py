"""Batch engine: validate → execute → stop. MockBackend only."""
import threading
import time

from jarvis.automation.engine import AutomationEngine, MockBackend


def test_safe_batch_executes():
    backend = MockBackend()
    engine = AutomationEngine(backend=backend)
    report = engine.run_batch([
        {"type": "open_app", "app": "blender"},
        {"type": "wait", "seconds": 0.1},
        {"type": "click", "x": 100, "y": 100},
        {"type": "key", "key": "enter"},
        {"type": "type", "text": "hello"},
    ], task="demo")
    assert report["done"] == 5 and report["failed"] == 0
    assert [c["call"] for c in backend.calls] == [
        "open_app", "click", "key", "type"]


def test_deny_dropped_confirm_held():
    engine = AutomationEngine(backend=MockBackend())
    report = engine.run_batch([
        {"type": "format_disk"},
        {"type": "shell", "command": "rm -rf ~"},
        {"type": "shell", "command": "apt_update"},
        {"type": "open_app", "app": "x"},
    ], require_confirm=True)
    assert report["failed"] == 2 and len(report["denied"]) == 2
    assert len(report["needs_confirm"]) == 1
    assert report["done"] == 1


def test_confirm_callback_approves():
    engine = AutomationEngine(backend=MockBackend())
    report = engine.run_batch(
        [{"type": "shell", "command": "apt_update"}],
        require_confirm=True, confirm_callback=lambda q: True)
    assert report["done"] == 1


def test_emergency_stop():
    engine = AutomationEngine(backend=MockBackend())

    def stopper():
        time.sleep(0.15)
        engine.stop()

    threading.Thread(target=stopper, daemon=True).start()
    report = engine.run_batch([{"type": "wait", "seconds": 0.2}] * 20)
    assert report["stopped"] is True
    assert report["done"] < 20


def test_batch_size_cap():
    engine = AutomationEngine(backend=MockBackend())
    report = engine.run_batch([{"type": "wait", "seconds": 0.1}] * 100)
    assert report["total"] == engine.MAX_BATCH
