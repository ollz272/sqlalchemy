.. change::
    :tags: performance, orm

    Improved the performance of relationship population for
    :func:`_orm.selectinload`.  The "SELECT .. IN" query now selects a
    single-column key directly rather than wrapping it in a
    :class:`.Bundle`, avoiding construction of a nested :class:`.Row` per
    result row, and the loader consumes interim row tuples directly when
    no uniquing is required, skipping per-row :class:`.Row` object
    construction entirely.  Many-to-one selectin loads additionally use a
    fast path to extract foreign key values from the parent instances,
    and :func:`_orm.subqueryload` groups its result on plain tuples
    rather than :class:`.Row` slices.
