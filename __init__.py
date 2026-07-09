bl_info = {
    "name": "Gravity UV",
    "author": "mexanik01",
    "version": (5, 0),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > Gravity UV",
    "description": "Выравнивание UV по гравитации с сохранением масштаба и кэшем каналов",
    "category": "UV",
}

import bpy

# Логика автоперезагрузки модулей при повторном включении аддона в Blender
if "operators" in locals():
    import importlib
    importlib.reload(properties)
    importlib.reload(operators)
    importlib.reload(ui)
    importlib.reload(material)
    importlib.reload(core)
else:
    from . import properties
    from . import operators
    from . import ui
    from . import material
    from . import core

classes = (
    operators.UV_OT_gravity_unwrap,
    operators.UV_OT_gravity_align,
    ui.UV_PT_gravity_panel,
)

def register():
    properties.register()
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    properties.unregister()

if __name__ == "__main__":
    register()
