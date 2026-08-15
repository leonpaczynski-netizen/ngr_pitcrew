"""The physical rig: what the app drives rather than what it reads.

Everything else in Pit Crew observes. This package acts - fans, and in time a
tactile transducer - which changes the rules in one important way:

**An output must never be able to stop the app recording a session.** A
missing `pyserial`, an unplugged Arduino, a COM port someone else is holding,
a sound card that vanished - each of those makes one output unavailable and
none of them is allowed to cost the driver his practice data. Every entry
point here fails soft and says so, rather than raising into the telemetry
path.

The second rule comes from watching the thing this replaces. SimHub's
"constant crashes" were a three-thread deadlock in its serial layer:
`SerialDashController.Send` called `Close()` on the port from inside the send
path while the reader thread was parked in `EndRead` on the same handle, and a
third thread waited on both. Windows logged it as a hang, never a crash, and
the process survived a force-kill with its last thread in an unkillable
kernel wait. So: **never close a port from inside a write.** Ownership of a
handle belongs to one thread, and teardown is that thread's business.
"""
