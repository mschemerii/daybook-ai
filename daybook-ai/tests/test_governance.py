def test_user_controlled_memory(governance):
    mid = governance.create_memory("First")
    assert governance.list_memories()[0]["content"] == "First"
    governance.update_memory(mid, "Updated")
    assert governance.list_memories()[0]["content"] == "Updated"
    governance.delete_memory(mid)
    assert governance.list_memories() == []


def test_audit_history_deletion(governance):
    aid = governance.add_audit("request", [{"type":"task","id":1}], "answer")
    assert governance.list_audit()[0]["id"] == aid
    governance.delete_audit(aid)
    assert governance.list_audit() == []
