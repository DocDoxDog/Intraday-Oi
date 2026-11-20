# Intraday-OI Knowledge Graph

## Core graph

KNOWLEDGE -> SUPPORTS -> SKILL -> APPLIES_TO -> SITUATION -> PRODUCES -> EVENT -> ACTIVATES -> MECHANISM -> CHANGES -> PRICE_RESPONSE -> PRODUCES -> OUTCOME -> UPDATES -> KNOWLEDGE

## Node types

KNOWLEDGE, SKILL, MECHANISM, SITUATION, EVENT, OBSERVATION, SIGNAL, SCENARIO, TRADE, OUTCOME, RULE, HYPOTHESIS, EVIDENCE, FAILURE.

## Mechanism map

Mean reversion:
deviation -> rejection/reclaim -> return toward reference.

Momentum / expansion:
displacement + flow alignment + liquidity withdrawal + acceptance -> continuation.

Absorption:
aggressive flow rises while price response stays weak -> opposing liquidity may be absorbing flow.

Liquidity sweep:
price reaches liquidity -> sweep -> reject, accept, reclaim or expand.

Gamma feedback:
options positioning changes sensitivity to price movement. Treat as mechanism/regime evidence, not guaranteed direction.

Reflexivity:
price changes positioning and expectations; those changes feed back into price.

Cascade:
one move triggers hedging, stops, risk reduction or positioning changes, producing secondary moves.

Liquidity vacuum:
available liquidity falls -> price can travel farther for the same flow.

Volatility clustering:
high-volatility states can persist.

Phase transition:
market behavior shifts from range-like to trend-like or vice versa.

## Scenario graph

Gamma break + acceptance + flow follows + structure aligned
-> CONTINUATION -> NEXT WALL

Gamma break + weak response + reclaim
-> FAILED BREAK -> MEAN REVERSION

Wall holds + absorption + no displacement
-> RANGE / NO TRADE

## Evidence rule

Do not count correlated indicators as independent votes.
Confidence must come from independent evidence or a validated mechanism.

## Knowledge lifecycle

IDEA -> TESTING -> PROMISING -> VALIDATED -> REJECTED -> DEPRECATED

Rejected hypotheses remain in history so the system does not repeatedly rediscover failed ideas.
