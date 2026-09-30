# CFD MAPPING

Status: IMPLEMENTATION IN PROGRESS

The commercial product uses a configurable reference relationship between a
broker CFD symbol and a canonical reference market.

Required fields:

broker
cfd_symbol
canonical_reference
mapping_version
effective_from
effective_to

Examples are mappings to validate, not hard-coded production truth:

XAUUSD CFD → GC reference
USOIL CFD → CL/oil reference
UKOIL CFD → Brent reference
NAS100 CFD → NQ reference

A customer's broker price remains distinct from the canonical reference price.

Customer-facing views must label:
Reference Market
CFD Broker Price
Data Timestamp

No code may assume that a CME futures quote is the customer's executable CFD price.
