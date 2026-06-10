.. change::
    :tags: performance, orm

    Added a Cython-compiled batch instance processor for ORM entity
    loading, improving the performance of entity hydration, in
    particular for :func:`_orm.selectinload` collection loads which are
    35-45% faster in typical cases when combined with the other
    hydration improvements in this series.  The batch processor handles
    the common case of rows producing new instances with per-query
    constant conditions hoisted out of the per-row loop, applies column
    values by position into the instance dict, and delegates rows for
    instances already present in the identity map to the previous
    per-row logic, which also remains in use for refresh operations and
    polymorphic loads.
