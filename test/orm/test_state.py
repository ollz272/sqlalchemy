"""Behaviour-locking tests for InstanceState._commit and
_commit_all_states.

These tests pin the exact post-conditions of the commit routines on
``committed_state``, ``expired_attributes``, ``callables`` and the
``modified`` / ``expired`` flags.  They exist to guard against subtle
end-state regressions in the commit code paths (e.g. when the empty-collection
work is guarded behind truthiness checks for performance).

"""

from sqlalchemy import inspect
from sqlalchemy.orm import attributes
from sqlalchemy.orm import deferred
from sqlalchemy.testing import eq_
from sqlalchemy.testing import is_false
from sqlalchemy.testing import is_true
from sqlalchemy.testing.fixtures import fixture_session
from test.orm import _fixtures


class CommitEndStateTest(_fixtures.FixtureTest):
    """End-to-end coverage: load / expire / refresh round trips and the
    resulting state of committed_state / expired_attributes / flags."""

    run_inserts = "each"
    run_deletes = "each"

    def test_full_load_fresh_instance(self):
        """1. A plain full load leaves both collections empty and the
        modified / expired flags False."""

        users, User = self.tables.users, self.classes.User
        self.mapper_registry.map_imperatively(User, users)

        sess = fixture_session(autoflush=False)
        u = sess.get(User, 7)

        state = inspect(u)
        eq_(state.committed_state, {})
        eq_(state.expired_attributes, set())
        is_false(state.modified)
        is_false(state.expired)

    def test_deferred_column_load(self):
        """2. A deferred column is listed in expired_attributes after a
        full expire; accessing a non-deferred attr clears expired_attributes
        but does NOT populate the deferred column into state.dict, which is
        only loaded on its own access."""

        Order, orders = self.classes.Order, self.tables.orders
        self.mapper_registry.map_imperatively(
            Order,
            orders,
            properties={"description": deferred(orders.c.description)},
        )

        sess = fixture_session(autoflush=False)
        o1 = sess.get(Order, 1)
        state = inspect(o1)

        # fresh load: nothing pending, nothing expired, description not loaded
        eq_(state.committed_state, {})
        eq_(state.expired_attributes, set())
        assert "description" not in o1.__dict__

        # now expire everything -> the deferred column is included
        sess.expire(o1)
        eq_(
            state.expired_attributes,
            {"id", "user_id", "description", "isopen", "address_id"},
        )

        # access a non-deferred expired attr.  This unexpires the row and
        # clears expired_attributes entirely, but the deferred column is
        # NOT populated into state.dict.
        assert o1.isopen is not None
        eq_(state.expired_attributes, set())
        assert "description" not in o1.__dict__

        # accessing description loads it via its deferred callable; the
        # post-load _commit leaves expired_attributes empty.
        assert o1.description == "order 1"
        eq_(state.expired_attributes, set())

    def test_expire_then_partial_refresh(self):
        """3. expire a subset, then load only some of them: only the keys
        loaded AND present in the state dict leave expired_attributes; the
        rest stay expired (the documented _commit contract)."""

        Order, orders = self.classes.Order, self.tables.orders
        self.mapper_registry.map_imperatively(Order, orders)

        sess = fixture_session(autoflush=False)
        o1 = sess.get(Order, 1)
        state = inspect(o1)

        # expire two specific attributes
        sess.expire(o1, ["isopen", "description"])
        eq_(state.expired_attributes, {"isopen", "description"})

        # partial refresh: reload ONLY 'isopen'.  This drives the _commit
        # contract directly - only the loaded-and-populated key leaves
        # expired_attributes.
        sess.refresh(o1, ["isopen"])
        eq_(o1.isopen, 0)

        # 'isopen' was populated, so it leaves expired_attributes; but
        # 'description' was never repopulated, so it remains expired.
        eq_(state.expired_attributes, {"description"})
        assert "description" not in o1.__dict__

        # the expired flag is reset by _commit even though a key remains
        is_false(state.expired)

    def test_populate_existing_reload(self):
        """5. populate_existing=True reload over an existing, modified
        instance resets committed_state / expired / modified."""

        users, User = self.tables.users, self.classes.User
        self.mapper_registry.map_imperatively(User, users)

        sess = fixture_session(autoflush=False)
        u = sess.get(User, 7)

        # dirty the instance so committed_state / modified are populated
        u.name = "changed"
        state = inspect(u)
        is_true(state.modified)
        eq_(state.committed_state, {"name": "jack"})

        # reload over it
        u2 = sess.query(User).populate_existing().filter_by(id=7).one()
        assert u2 is u

        # populate_existing performs a full refresh -> _commit_all clears it
        eq_(u.name, "jack")
        eq_(state.committed_state, {})
        eq_(state.expired_attributes, set())
        is_false(state.modified)
        is_false(state.expired)

    def test_modified_then_flush_commit_all(self):
        """6. A genuinely modified instance (non-empty committed_state) gets
        its committed_state cleared and modified reset on flush."""

        users, User = self.tables.users, self.classes.User
        self.mapper_registry.map_imperatively(User, users)

        sess = fixture_session(autoflush=False)
        u = sess.get(User, 8)

        u.name = "newname"
        state = inspect(u)
        is_true(state.modified)
        eq_(state.committed_state, {"name": "ed"})
        assert u in sess.dirty
        assert state in sess._dirty_states

        sess.flush()

        # flush runs _commit_all_states -> committed_state cleared,
        # modified reset, expired stays False
        eq_(state.committed_state, {})
        eq_(state.expired_attributes, set())
        is_false(state.modified)
        is_false(state.expired)
        assert u not in sess.dirty
        assert state not in sess._dirty_states


class CommitDirectUnitTest(_fixtures.FixtureTest):
    """Direct unit-level invocation of _commit / _commit_all_states with
    hand-built collection contents, to cover both the guarded no-op path
    (empty collections) and the active path (non-empty)."""

    run_inserts = None

    def _user_state(self):
        users, User = self.tables.users, self.classes.User
        self.mapper_registry.map_imperatively(User, users)
        u = User(name="x")
        state = inspect(u)
        dict_ = state.dict
        # simulate a clean load: place values directly into the dict, then
        # commit_all once to clear the committed_state left over from
        # __init__ (which records {'name': NO_VALUE}).  This gives us a
        # state with genuinely empty committed_state / expired_attributes
        # to start from.
        dict_["id"] = 1
        dict_["name"] = "x"
        state._commit_all(dict_)
        return state, dict_

    # ---- _commit -------------------------------------------------------

    def test_commit_empty_collections_noop(self):
        """7 (empty path). _commit with empty committed_state and empty
        expired_attributes leaves them empty and resets expired."""

        state, dict_ = self._user_state()
        eq_(state.committed_state, {})
        eq_(state.expired_attributes, set())
        state.expired = True

        state._commit(dict_, ["id", "name"])

        eq_(state.committed_state, {})
        eq_(state.expired_attributes, set())
        is_false(state.expired)

    def test_commit_nonempty_collections_active(self):
        """7 (active path). _commit with non-empty committed_state and
        expired_attributes pops the given keys from committed_state and
        difference_updates expired_attributes by keys present in the
        state dict."""

        state, dict_ = self._user_state()

        state.committed_state["id"] = 0
        state.committed_state["name"] = "old"
        # 'extra' is committed but not a commit key -> should remain
        state.committed_state["extra"] = "keepme"

        # expired: 'name' present in dict_, 'absent' not present in dict_
        state.expired_attributes.update(["name", "absent"])
        state.expired = True

        # keys include one present in dict_ ('name'), one absent from
        # dict_ ('absent'), and one not expired ('id').
        state._commit(dict_, ["id", "name", "absent"])

        # committed_state: the listed keys are popped, 'extra' remains
        eq_(state.committed_state, {"extra": "keepme"})

        # expired_attributes: only keys in keys AND in dict_ are removed.
        # 'name' is in dict_ -> removed.  'absent' is NOT in dict_ -> stays.
        eq_(state.expired_attributes, {"absent"})

        is_false(state.expired)

    def test_commit_keys_present_and_absent_from_dict(self):
        """7 (mixed keys). Cover keys that are both present in and absent
        from the state dict in the same call: only the present ones clear
        expiry."""

        state, dict_ = self._user_state()
        # dict_ has 'id' and 'name'.  Add a third expired key not in dict_.
        state.expired_attributes.update(["id", "name", "phantom"])

        state._commit(dict_, ["id", "name", "phantom"])

        # 'id' and 'name' present -> cleared; 'phantom' absent -> remains
        eq_(state.expired_attributes, {"phantom"})

    def test_commit_callables_intersection(self):
        """4. _commit removes only callables whose key is in
        set(callables) AND keys AND the state dict."""

        state, dict_ = self._user_state()

        def _cb(state, passive):
            return attributes.ATTR_EMPTY

        # 'name' -> in keys and in dict_ -> removed
        # 'id'   -> in keys and in dict_ -> removed
        # 'gone' -> in keys but NOT in dict_ -> kept
        # 'other'-> in dict_ but NOT in keys -> kept
        dict_["other"] = "v"
        state.callables = {
            "name": _cb,
            "id": _cb,
            "gone": _cb,
            "other": _cb,
        }

        state._commit(dict_, ["id", "name", "gone"])

        eq_(set(state.callables), {"gone", "other"})

    def test_commit_empty_callables_untouched(self):
        """4 (guard). With no callables, _commit leaves callables empty."""

        state, dict_ = self._user_state()
        # default empty callables
        state._commit(dict_, ["id", "name"])
        eq_(dict(state.callables), {})

    # ---- _commit_all_states -------------------------------------------

    def test_commit_all_states_empty_noop(self):
        """7 (empty path, mass). _commit_all_states with empty collections
        leaves them empty and resets modified / expired."""

        state, dict_ = self._user_state()
        eq_(state.committed_state, {})
        eq_(state.expired_attributes, set())
        state.modified = True
        state.expired = True

        state._commit_all_states([(state, dict_)])

        eq_(state.committed_state, {})
        eq_(state.expired_attributes, set())
        is_false(state.modified)
        is_false(state.expired)

    def test_commit_all_states_nonempty_active(self):
        """7 (active path, mass). _commit_all_states clears committed_state
        entirely and difference_updates expired_attributes by the state
        dict."""

        state, dict_ = self._user_state()

        state.committed_state["id"] = 0
        state.committed_state["name"] = "old"
        # expired: 'name' present in dict_, 'phantom' not present in dict_
        state.expired_attributes.update(["name", "phantom"])
        state.modified = True
        state.expired = True

        state._commit_all_states([(state, dict_)])

        # committed_state cleared wholesale
        eq_(state.committed_state, {})

        # expired_attributes difference_updated by the *whole* dict_, so any
        # expired key present in dict_ is removed; 'phantom' (absent) stays.
        eq_(state.expired_attributes, {"phantom"})

        is_false(state.modified)
        is_false(state.expired)

    def test_commit_all_states_keys_present_and_absent(self):
        """7 (mixed, mass). Expired keys both present in and absent from
        the state dict: only the present ones are removed."""

        state, dict_ = self._user_state()
        state.expired_attributes.update(["id", "name", "absent"])

        state._commit_all_states([(state, dict_)])

        eq_(state.expired_attributes, {"absent"})

    def test_commit_all_does_not_touch_callables(self):
        """_commit_all (single) does NOT remove object-level callables,
        unlike _commit (documented difference)."""

        state, dict_ = self._user_state()

        def _cb(state, passive):
            return attributes.ATTR_EMPTY

        state.callables = {"name": _cb, "id": _cb}
        state._commit_all(dict_)

        # callables are deliberately left alone by _commit_all
        eq_(set(state.callables), {"name", "id"})
