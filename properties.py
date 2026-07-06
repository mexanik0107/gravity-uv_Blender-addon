import bpy
from .material import setup_gravity_material

def update_uv_preview_toggle(self, context):
    for obj in context.scene.objects:
        if obj.type == 'MESH':
            grav_uv = obj.data.uv_layers.get("Gravity_UV")
            if grav_uv:
                if context.scene.preview_gravity_uv:
                    obj.data.uv_layers.active = grav_uv
                else:
                    # Возвращаем оригинальную карту из кэша объекта
                    orig_name = obj.gravity_uv_original_name
                    orig_uv = obj.data.uv_layers.get(orig_name) if orig_name else None
                    if not orig_uv and len(obj.data.uv_layers) > 1:
                        for layer in obj.data.uv_layers:
                            if layer.name != "Gravity_UV":
                                orig_uv = layer
                                break
                    if orig_uv:
                        obj.data.uv_layers.active = orig_uv
                        
                setup_gravity_material(obj, context.scene)

def update_scene_views(self, context):
    for obj in context.scene.objects:
        if obj.type == 'MESH' and "Gravity_UV" in obj.data.uv_layers:
            setup_gravity_material(obj, context.scene)

def update_object_views(self, context):
    if self.type != 'MESH':
        return
    if "Gravity_UV" in self.data.uv_layers:
        setup_gravity_material(self, context.scene)

def register():
    bpy.types.Object.gravity_uv_original_name = bpy.props.StringProperty(name="Original UV Name", default="")
    bpy.types.Object.gravity_uv_cache_mat = bpy.props.StringProperty(name="Cached Material", default="")
    bpy.types.Object.gravity_uv_filepath = bpy.props.StringProperty(
        name="Файл текстуры", subtype='FILE_PATH', update=update_object_views
    )
    bpy.types.Object.gravity_uv_use_local_coplanar = bpy.props.BoolProperty(
        name="Локальное искривление", default=False, update=update_object_views
    )
    bpy.types.Object.gravity_uv_local_coplanar_threshold = bpy.props.FloatProperty(
        name="Локальное искривление плоскости", default=0.0872665, min=0.0, max=0.785398, subtype='ANGLE',
        description="Максимальный угол между нормалями для этого объекта при выравнивании",
        update=update_object_views
    )
    
    # Глобальный тумблер переключения превью карт на сцене
    bpy.types.Scene.preview_gravity_uv = bpy.props.BoolProperty(
        name="Превью Gravity_UV", default=True, update=update_uv_preview_toggle
    )
    bpy.types.Scene.pack_after_align = bpy.props.BoolProperty(
        name="Упаковать после выравнивания", default=True
    )
    bpy.types.Scene.gravity_uv_coplanar_threshold = bpy.props.FloatProperty(
        name="Искривление плоскости", default=0.0872665, min=0.0, max=0.785398, subtype='ANGLE',
        description="Максимальный угол между нормалями для объединения в одну плоскость",
        update=update_scene_views
    )
    bpy.types.Scene.gravity_uv_flat_threshold = bpy.props.FloatProperty(
        name="Погрешность горизонтали", default=0.1000073, min=0.0, max=0.785398, 
        step=0.017453292, precision=2, subtype='ANGLE',
        description="Допустимый угол отклонения от вертикали для плоских граней",
        update=update_scene_views
    )
    
    bpy.types.Scene.show_debug_arrows = bpy.props.BoolProperty(
        name="Показывать стрелки", default=True, update=update_scene_views
    )
    bpy.types.Scene.show_flat_highlight = bpy.props.BoolProperty(
        name="Показывать полосы", default=False, update=update_scene_views
    )
    bpy.types.Scene.gravity_uv_scale = bpy.props.FloatProperty(
        name="Масштаб", default=4.0, min=0.1, max=100.0, update=update_scene_views
    )
    bpy.types.Scene.flat_faces_mode = bpy.props.EnumProperty(
        name="Плоские грани",
        items=[('IGNORE', 'Не учитывать', 'Оставить как есть'),
               ('ALIGN', 'Повернуть на угол', 'Задать базовое направление')],
        default='IGNORE', update=update_scene_views
    )
    bpy.types.Scene.flat_faces_angle = bpy.props.FloatProperty(
        name="Угол", default=0.0, min=0.0, max=6.28318, subtype='ANGLE', update=update_scene_views
    )

def unregister():
    del bpy.types.Object.gravity_uv_original_name
    del bpy.types.Object.gravity_uv_cache_mat
    del bpy.types.Object.gravity_uv_filepath
    del bpy.types.Object.gravity_uv_use_local_coplanar
    del bpy.types.Object.gravity_uv_local_coplanar_threshold
    del bpy.types.Scene.preview_gravity_uv
    del bpy.types.Scene.pack_after_align
    del bpy.types.Scene.gravity_uv_coplanar_threshold
    del bpy.types.Scene.gravity_uv_flat_threshold
    del bpy.types.Scene.show_debug_arrows
    del bpy.types.Scene.show_flat_highlight
    del bpy.types.Scene.gravity_uv_scale
    del bpy.types.Scene.flat_faces_mode
    del bpy.types.Scene.flat_faces_angle
