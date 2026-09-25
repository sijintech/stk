"""Clean-room analysis kernels (docs/specs/domain-classifiers.md): NumPy only, no VTK.

* ``orientation``: generated direction sets (``stk:cubic-26`` and subsets), the
  vectorized orientation classifier and HSL orientation colours;
* ``labels``: film/substrate detection and label fractions;
* ``palettes``: categorical palettes (``stk:categorical``,
  ``stk:cubic-26-orientation``, ``stk-legacy:ferro27``).

``palettes`` and the direction tables need only the standard library; array
functions import NumPy when called.
"""
