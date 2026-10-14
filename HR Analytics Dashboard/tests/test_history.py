from core.history import History


def test_undo_redo_walks_through_states():
    h = History({'n': 0})
    h.push({'n': 1}, 'one')
    h.push({'n': 2}, 'two')
    assert h.undo() == {'n': 1}
    assert h.undo() == {'n': 0}
    assert h.undo() is None
    assert h.redo() == {'n': 1}
    assert h.redo() == {'n': 2}
    assert h.redo() is None


def test_labels_name_the_action_being_reversed_or_reapplied():
    h = History({'n': 0})
    h.push({'n': 1}, 'Add series')
    assert h.undo_label() == 'Add series' and h.redo_label() == ''
    h.undo()
    assert h.undo_label() == '' and h.redo_label() == 'Add series'


def test_new_edit_after_undo_discards_redo():
    h = History({'n': 0})
    h.push({'n': 1}, 'a')
    h.undo()
    h.push({'n': 5}, 'b')
    assert not h.can_redo()
    assert h.undo() == {'n': 0}


def test_identical_state_is_not_recorded():
    h = History({'n': 0})
    assert h.push({'n': 0}, 'no-op') is False
    assert not h.can_undo()


def test_snapshots_are_isolated_from_later_mutation():
    state = {'charts': [{'series': []}]}
    h = History(state)
    state['charts'][0]['series'].append('x')
    h.push(state, 'add')
    state['charts'][0]['series'].append('y')
    restored = h.undo()
    assert restored == {'charts': [{'series': []}]}
    restored['charts'].append('junk')
    assert h.redo() == {'charts': [{'series': ['x']}]}


def test_limit_drops_oldest_entries():
    h = History({'n': 0}, limit=3)
    for i in range(1, 6):
        h.push({'n': i}, str(i))
    assert len(h) == 3
    assert h.undo() == {'n': 4}
    assert h.undo() == {'n': 3}
    assert h.undo() is None
