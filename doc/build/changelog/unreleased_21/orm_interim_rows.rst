.. change::
    :tags: performance, orm, engine

    ORM entity loading now processes database rows as plain tuples with
    result processors applied, rather than constructing a
    :class:`.Row` object for every row.  ORM row getters are
    position-based and accept any tuple-like row, so behavior is
    unchanged; Row construction is still used for results that require
    row logging or scalar sources.
