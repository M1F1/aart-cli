"""Stable process exit codes shared by the canonical command skins."""

OK = 0
ERROR = 1
USAGE = 2
NETWORK = 3
CONFLICT = 4
CORRUPT_MANIFEST = 5


class Findings(int):
    """A nonzero exit that reports what a check found, not a failure of the command.

    Its value is the exit code a script reads, unchanged; its type is what tells the failure
    journal that nothing went wrong while checking (§215, D-534).
    """


#: `doctor` read everything and found something that needs attention.
FOUND = Findings(ERROR)
