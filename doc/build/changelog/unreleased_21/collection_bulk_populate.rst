.. change::
    :tags: performance, orm

    Eager-load population of the default list-based relationship
    collection now uses ``list.extend()`` rather than per-item
    instrumented appends; with events disabled the instrumented append
    reduces to ``list.append``, so behavior is unchanged.
