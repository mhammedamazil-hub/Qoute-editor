from minicoder.working_memory import WorkingMemory


def test_capacity_eviction_spares_pinned(brain_home):
    wm = WorkingMemory()
    wm.capacity = 4
    wm.add("pinned-critical", priority=0.1, pinned=True)
    for i in range(6):
        wm.add(f"noise-{i}", priority=0.2)
    contents = [i.content for i in wm.items]
    assert "pinned-critical" in contents
    assert len(wm.items) == 4


def test_pin_budget_enforced(brain_home):
    wm = WorkingMemory()
    wm.pinned_max = 2
    a = wm.add("a", pinned=True)
    b = wm.add("b", pinned=True)
    c = wm.add("c", pinned=True)
    pinned = [i.content for i in wm.items if i.pinned]
    assert len(pinned) == 2  # weakest pin got demoted, never exceeds budget


def test_empty_content_rejected(brain_home):
    wm = WorkingMemory()
    try:
        wm.add("   ")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_context_block_respects_priority(brain_home):
    wm = WorkingMemory()
    wm.add("low-priority-fact", priority=0.1)
    wm.add("CRITICAL CONSTRAINT", priority=0.99, pinned=True)
    block = wm.context_block()
    assert block.index("CRITICAL CONSTRAINT") < block.index("low-priority-fact")
