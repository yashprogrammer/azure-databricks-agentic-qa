"""AI Credit Memo Draft: the integration of PolicyPilot into Contoso Bank's Credit Portal.

Each of the six credit memo sections is drafted by its own agent run (guard -> plan ->
retrieve -> draft -> verify), stored as a versioned, fully traced draft, and only reaches the
legacy memo after an analyst approves it.
"""
