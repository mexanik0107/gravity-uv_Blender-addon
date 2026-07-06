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
        
        if not obj or obj.type != 'MESH':
            layout.label(text="Выберите полигональный объект", icon='ERROR')
            return
            
        box_prep = layout.box()
        box_prep.label(text="1. Подготовка (Поддерживает Batch):", icon='MESH_DATA')
        box_prep.operator("uv.gravity_unwrap", text="Пересоздать развертку", icon='UV_DATA')
        
        box_action = layout.box()
        box_action.label(text="2. Выравнивание (Создать 2-й канал):", icon='WORLD_DATA')
        box_action.operator("uv.gravity_align", text="Выровнять по Гравитации", icon='OBJECT_DATA')
        box_action.prop(scene, "gravity_uv_coplanar_threshold", text="Искривление плоскости")
        
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
            
        selected_meshes = [o for o in context.selected_objects if o.type == 'MESH']
        
        box_mesh = layout.box()
        box_mesh.label(text="5. Настройки меша:", icon='MESH_DATA')
        
        if len(selected_meshes) <= 1:
            box_mesh.prop(obj, "gravity_uv_use_local_coplanar", text="Собственное искривление")
            if obj.gravity_uv_use_local_coplanar:
                box_mesh.prop(obj, "gravity_uv_local_coplanar_threshold", text="Искривление плоскости")
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
                box_mesh.prop(obj, "gravity_uv_use_local_coplanar", text=f"Включить для активного ({obj.name})")
