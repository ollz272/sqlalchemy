.. change::
    :tags: performance, orm

    ``InstanceState`` now creates its ``committed_state`` dictionary and
    ``expired_attributes`` set lazily on first access, avoiding two
    container allocations per loaded instance for objects that are never
    subsequently mutated or expired.
