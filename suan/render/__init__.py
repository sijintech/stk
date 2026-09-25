"""STK rendering: render payload v2, scene v1 downgrade, colormaps and the offscreen VTK renderer.

* ``suan.render.layers``    -- in-memory layers and scenes (graph port types ``layer``/``scene``)
* ``suan.render.payload``   -- ``stk.payload/2`` encode/decode/validate and ``.stkp`` files
* ``suan.render.v1``        -- downgrade to scene v1 for ``stk.scene/1`` clients
* ``suan.render.colormaps`` -- LUTs, ``stk:orientation-hsl``, categorical palettes, transfer functions
* ``suan.render.offscreen`` -- PNGs from payloads, VTK always in a child process

Importing this package imports nothing heavy (NumPy/VTK are loaded lazily).
See docs/specs/stk-render-payload-v2.md.
"""
