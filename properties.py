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

def update_interactive_solver(self, context):
    """
    Вызывает интерактивный расчет Фазы Б для всех выделенных мешей с каналом Gravity_UV.
    Это дает 60 FPS во вьюпорте при перемещении интерактивных ползунков.
    """
    import time
    t0 = time.perf_counter()
    from .core import solve_gravity_uv
    scene = context.scene
    meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
    count = 0
    for obj in meshes:
        if "Gravity_UV" in obj.data.uv_layers:
            solve_gravity_uv(obj, scene)
            setup_gravity_material(obj, scene)
            count += 1
    t_total = (time.perf_counter() - t0) * 1000
    if count > 0:
        print(f"[Gravity UV] >>> Обновление 3D-направления: {t_total:.2f} мс для {count} объектов")

def update_rebuild_cache(self, context):
    """
    Инвалидирует старый кэш и принудительно запускает Фазу А и Фазу Б
    при изменении параметров, влияющих на структуру островов.
    """
    import time
    t0 = time.perf_counter()
    from .core import clear_gravity_uv_cache, solve_gravity_uv
    scene = context.scene
    meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
    count = 0
    for obj in meshes:
        clear_gravity_uv_cache(obj)
        if "Gravity_UV" in obj.data.uv_layers:
            solve_gravity_uv(obj, scene)
            setup_gravity_material(obj, scene)
            count += 1
    t_total = (time.perf_counter() - t0) * 1000
    if count > 0:
        print(f"[Gravity UV] >>> Перестроение кэша (Фаза А) и расчет: {t_total:.2f} мс для {count} объектов")

def register():
    bpy.types.Object.gravity_uv_original_name = bpy.props.StringProperty(name="Original UV Name", default="")
    bpy.types.Object.gravity_uv_cache_mat = bpy.props.StringProperty(name="Cached Material", default="")
    bpy.types.Object.gravity_uv_filepath = bpy.props.StringProperty(
        name="Файл текстуры", subtype='FILE_PATH', update=update_object_views
    )
    bpy.types.Object.gravity_uv_use_local_coplanar = bpy.props.BoolProperty(
        name="Локальное искривление", default=False, update=update_rebuild_cache
    )
    bpy.types.Object.gravity_uv_local_coplanar_threshold = bpy.props.FloatProperty(
        name="Локальное искривление плоскости", default=0.0872665, min=0.0, max=0.785398, subtype='ANGLE',
        description="Максимальный угол между нормалями для этого объекта при выравнивании",
        update=update_rebuild_cache
    )
    
    # Глобальный тумблер переключения превью карт на сцене
    bpy.types.Scene.preview_gravity_uv = bpy.props.BoolProperty(
        name="Превью Gravity_UV", default=True, update=update_uv_preview_toggle
    )
    bpy.types.Scene.pack_after_align = bpy.props.BoolProperty(
        name="Упаковать после выравнивания", default=True
    )
    bpy.types.Scene.gravity_uv_rotation_mode = bpy.props.EnumProperty(
        name="Режим вращения",
        items=[('ISLANDS', 'Целые острова', 'Каждый остров вращается как единое целое без образования внутренних швов'),
               ('COPLANAR', 'По плоскостям', 'Острова разбиваются на плоскости и вращаются независимо для идеальной вертикали')],
        default='ISLANDS', update=update_rebuild_cache
    )
    bpy.types.Scene.gravity_uv_coplanar_threshold = bpy.props.FloatProperty(
        name="Искривление плоскости", default=0.0872665, min=0.0, max=0.785398, subtype='ANGLE',
        description="Максимальный угол между нормалями для объединения в одну плоскость",
        update=update_rebuild_cache
    )
    bpy.types.Scene.gravity_uv_flat_threshold = bpy.props.FloatProperty(
        name="Погрешность горизонтали", default=0.1000073, min=0.0, max=0.785398, 
        step=0.017453292, precision=2, subtype='ANGLE',
        description="Допустимый угол отклонения от вертикали для плоских граней",
        update=update_rebuild_cache  # Изменение этого порога влияет на то, какие полигоны плоские, поэтому перестраиваем кэш
    )
    
    # Умная проекция XY
    bpy.types.Scene.gravity_uv_use_xy_projection = bpy.props.BoolProperty(
        name="Проекция сверху вниз (XY)", default=False,
        description="Объединять изгибы по вертикали (например, цилиндрические крыши) в единые острова, игнорируя наклон",
        update=update_rebuild_cache
    )
    
    # Контроль закручивания для сложной геометрии
    bpy.types.Scene.gravity_uv_split_on_twist = bpy.props.BoolProperty(
        name="Контроль сложной геометрии", default=False,
        description="Разрезать UV остров, если направление гравитации на нем начинает закручиваться",
        update=update_rebuild_cache
    )
    bpy.types.Scene.gravity_uv_twist_threshold = bpy.props.FloatProperty(
        name="Порог закручивания", default=1.0471975, min=0.174533, max=3.14159, subtype='ANGLE',
        description="Максимальный угол закручивания гравитации на одном острове",
        update=update_rebuild_cache
    )
    
    # 3D Вектор гравитации / направления потеков
    bpy.types.Scene.gravity_uv_direction_x = bpy.props.FloatProperty(
        name="Направление X", default=0.0, min=-1.0, max=1.0,
        description="Отклонение потеков по горизонтали X (влево-вправо)",
        update=update_interactive_solver
    )
    bpy.types.Scene.gravity_uv_direction_y = bpy.props.FloatProperty(
        name="Направление Y", default=0.0, min=-1.0, max=1.0,
        description="Отклонение потеков по горизонтали Y (вперед-назад)",
        update=update_interactive_solver
    )
    bpy.types.Scene.gravity_uv_direction_z = bpy.props.FloatProperty(
        name="Направление Z", default=-1.0, min=-1.0, max=1.0,
        description="Отклонение потеков по вертикали Z (по умолчанию -1.0 - строго вниз)",
        update=update_interactive_solver
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
        default='IGNORE', update=update_interactive_solver
    )
    bpy.types.Scene.flat_faces_angle = bpy.props.FloatProperty(
        name="Угол", default=0.0, min=0.0, max=6.28318, subtype='ANGLE', update=update_interactive_solver
    )

def unregister():
    del bpy.types.Object.gravity_uv_original_name
    del bpy.types.Object.gravity_uv_cache_mat
    del bpy.types.Object.gravity_uv_filepath
    del bpy.types.Object.gravity_uv_use_local_coplanar
    del bpy.types.Object.gravity_uv_local_coplanar_threshold
    del bpy.types.Scene.preview_gravity_uv
    del bpy.types.Scene.pack_after_align
    del bpy.types.Scene.gravity_uv_rotation_mode
    del bpy.types.Scene.gravity_uv_coplanar_threshold
    del bpy.types.Scene.gravity_uv_flat_threshold
    del bpy.types.Scene.gravity_uv_use_xy_projection
    del bpy.types.Scene.gravity_uv_split_on_twist
    del bpy.types.Scene.gravity_uv_twist_threshold
    del bpy.types.Scene.gravity_uv_direction_x
    del bpy.types.Scene.gravity_uv_direction_y
    del bpy.types.Scene.gravity_uv_direction_z
    del bpy.types.Scene.show_debug_arrows
    del bpy.types.Scene.show_flat_highlight
    del bpy.types.Scene.gravity_uv_scale
    del bpy.types.Scene.flat_faces_mode
    del bpy.types.Scene.flat_faces_angle
