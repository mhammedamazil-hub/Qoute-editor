"""Safe file ops (tmp HOME) + /proc stats shapes."""
import os

from jarvis.control import filesops as F
from jarvis.system import stats as S


def test_new_folder_search_trash(tmp_home):
    ok, msg = F.new_folder("Demo", parent=str(tmp_home))
    assert ok and os.path.isdir(str(tmp_home / "Demo"))
    open(str(tmp_home / "Demo" / "presentation-draft.txt"), "w").write("x")
    hits = F.search("presentation", root=str(tmp_home))
    assert any("presentation-draft" in h for h in hits)
    ok, msg = F.move_to_trash(str(tmp_home / "Demo"))
    assert ok and not os.path.exists(str(tmp_home / "Demo"))
    ok, msg = F.empty_trash()
    assert ok


def test_protected_paths_refused(tmp_home):
    ok, msg = F.move_to_trash("/etc/hostname")
    assert ok is False
    assert F.search("x", root="/etc") == []


def test_stats_shapes():
    m = S.mem()
    assert m["total_mb"] > 0 and 0 <= m["percent"] <= 100
    d = S.disk("/")
    assert d["total_gb"] > 0
    assert 0 <= S.cpu_percent(interval=0.01) <= 100
    procs = S.top_processes(3)
    assert procs and procs[0]["rss_mb"] >= 0
    assert isinstance(S.summary(), dict)
