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
if "bpy" in locals():
    import importlib
    if "properties" in locals():
        importlib.reload(properties)
    if "operators" in locals():
        importlib.reload(operators)
    if "ui" in locals():
        importlib.reload(ui)
    if "material" in locals():
        importlib.reload(material)
    if "core" in locals():
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
