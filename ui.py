import bpy

class UV_PT_gravity_panel(bpy.types.Panel):
    """
    Интерфейсная панель во вьюпорте (N-панель) для плагина Gravity UV.
    """
    bl_label = "Gravity UV"
    bl_idname = "UV_PT_gravity_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Gravity UV"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = context.active_object
        
        selected_meshes = [o for o in context.selected_objects if o.type == 'MESH']
        
        # Умное определение: если активный объект не меш, но выделен хотя бы один меш,
        # используем первый выделенный меш для индивидуальных настроек
        if obj and obj.type == 'MESH':
            active_mesh = obj
        elif selected_meshes:
            active_mesh = selected_meshes[0]
        else:
            layout.label(text="Выберите полигональный объект", icon='ERROR')
            return
            
        box_prep = layout.box()
        box_prep.label(text="1. Подготовка (Поддерживает Batch):", icon='MESH_DATA')
        box_prep.operator("uv.gravity_unwrap", text="Пересоздать развертку", icon='UV_DATA')
        
        box_action = layout.box()
        box_action.label(text="2. Выравнивание (Создать 2-й канал):", icon='WORLD_DATA')
        box_action.operator("uv.gravity_align", text="Выровнять по Гравитации", icon='OBJECT_DATA')
        
        box_action.separator()
        box_action.prop(scene, "gravity_uv_rotation_mode", text="Режим работы")
        
        # Опции плоскостного режима
        if scene.gravity_uv_rotation_mode == 'COPLANAR':
            box_action.prop(scene, "gravity_uv_coplanar_threshold", text="Искривление плоскости")
            box_action.prop(scene, "gravity_uv_use_xy_projection", text="Проекция сверху вниз (XY)")
            
        box_action.prop(scene, "gravity_uv_split_on_twist", text="Контроль сложной геометрии")
        if scene.gravity_uv_split_on_twist:
            box_action.prop(scene, "gravity_uv_twist_threshold", text="Порог закручивания")
            
        # 3D Направление потеков
        box_action.separator()
        box_action.label(text="Направление потеков (3D):", icon='FORCE_WIND')
        col_dir = box_action.column(align=True)
        col_dir.prop(scene, "gravity_uv_direction_x", text="Ось X (Влево/Вправо)")
        col_dir.prop(scene, "gravity_uv_direction_y", text="Ось Y (Вперед/Назад)")
        col_dir.prop(scene, "gravity_uv_direction_z", text="Ось Z (Вверх/Вниз)")
        
        # Интерактивные галочки под кнопкой генерации
        box_action.separator()
        box_action.prop(scene, "preview_gravity_uv", text="Показывать карту Gravity_UV", icon='UV_SYNC_SELECT')
        box_action.prop(scene, "pack_after_align", text="Упаковать без масштабирования", icon='UV_DATA')
        
        box_tex = layout.box()
        box_tex.label(text="3. Управление текстурами:", icon='IMAGE_DATA')
        box_tex.prop(scene, "show_debug_arrows", text="Включить тестовые стрелки")
        box_tex.prop(scene, "gravity_uv_scale", text="Масштаб (тайлинг)")
        
        box_flat = layout.box()
        box_flat.label(text="4. Настройки плоских граней:", icon='COLOR')
        box_flat.prop(scene, "show_flat_highlight", text="Разметка плоских граней (Текстура)")
        box_flat.prop(scene, "gravity_uv_flat_threshold", text="Погрешность горизонтали")
        box_flat.prop(scene, "flat_faces_mode", text="Обработка")
        if scene.flat_faces_mode == 'ALIGN':
            box_flat.prop(scene, "flat_faces_angle", text="Угол поворота")
            
        box_mesh = layout.box()
        box_mesh.label(text="5. Настройки меша:", icon='MESH_DATA')
        
        if len(selected_meshes) <= 1:
            box_mesh.prop(active_mesh, "gravity_uv_use_local_coplanar", text="Собственное искривление")
            if active_mesh.gravity_uv_use_local_coplanar:
                box_mesh.prop(active_mesh, "gravity_uv_local_coplanar_threshold", text="Искривление плоскости")
        else:
            local_meshes = [o for o in selected_meshes if o.gravity_uv_use_local_coplanar]
            if local_meshes:
                box_mesh.label(text="Используют собственное искривление:", icon='INFO')
                for o in local_meshes:
                    row = box_mesh.row(align=True)
                    row.label(text=o.name, icon='OUTLINER_OB_MESH')
                    row.prop(o, "gravity_uv_local_coplanar_threshold", text="")
                    row.prop(o, "gravity_uv_use_local_coplanar", text="", icon='CANCEL')
            else:
                box_mesh.label(text="Индивидуальные настройки не заданы", icon='INFO')
                box_mesh.prop(active_mesh, "gravity_uv_use_local_coplanar", text=f"Включить для активного ({active_mesh.name})")
