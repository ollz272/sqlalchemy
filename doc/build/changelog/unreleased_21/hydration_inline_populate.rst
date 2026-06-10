.. change::
    :tags: performance, orm

    The full-population step that runs for each loaded ORM instance has
    been inlined into the per-row instance processor, removing a function
    call and several dictionary lookups per row for all entity loads.
