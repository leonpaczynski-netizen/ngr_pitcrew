"""Reading the NGR League Hub's own database.

The hub knows what Pit Crew was asking the driver to type in by hand: which
leagues he is in, which car in each, who his team mate is, who else is racing,
and every result of every round. This reads it - **read-only, never written
to** - so that none of it has to be maintained twice.

See `read.py` for the connection and `standings.py` for the championship
arithmetic, which is mirrored from the hub's own `src/lib/points.ts` rather
than invented.
"""
