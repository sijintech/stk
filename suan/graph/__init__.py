"""STK graph (stk.graph/1): node registry, validation and (Phase B) evaluation.

Importing this package must stay cheap and NumPy-free: the hub validates graphs
with ``suan.graph.schema.validate_graph`` in environments without NumPy. Node
implementations import heavy dependencies inside their functions.
"""
