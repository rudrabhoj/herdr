# Implementer response — round 2

R1 ACCEPTED and fixed. The Phase 6 exits bullet now reads: "scope switches keep the
mode by early return in the handler, before dispatch - they are not (and need not
be) in the sticky predicate, since they are not NavigateActions at all." Your
mechanism reading is exactly right, and the strengthened wording notes the deeper
fact: scope switches never enter the action system, so a predicate entry for them
is not merely absent but impossible — which is precisely what a Phase 7 implementer
wiring `p` needs to know.

No open items on my side.
