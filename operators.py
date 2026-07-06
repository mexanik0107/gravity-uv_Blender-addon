import bpy
import bmesh
from .core import align_mesh_by_gravity, pack_uv_islands_keep_scale
from .material import setup_gravity_material

class UV_OT_gravity_unwrap(bpy.types.Operator):
    """
    Массово пересоздает развертку для всех выделенных 3D-объектов.
    """
    bl_idname = "uv.gravity_unwrap"
    bl_label = "Пересоздать развертку"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not meshes:
            self.report({'WARNING'}, "Не выделено ни одного 3D-объекта!")
            return {'CANCELLED'}
            
        original_active = context.view_layer.objects.active
        for obj in meshes:
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.uv.select_all(action='SELECT')
            bpy.ops.uv.unwrap(margin=0.02)
            bmesh.update_edit_mesh(obj.data)
            
        if original_active:
            context.view_layer.objects.active = original_active
            bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}

class UV_OT_gravity_align(bpy.types.Operator):
    """
    Выравнивает развертку по вектору силы тяжести и упаковывает ее без изменения масштаба.
    """
    bl_idname = "uv.gravity_align"
    bl_label = "Выровнять по Гравитации"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not meshes:
            self.report({'WARNING'}, "Выделите хотя бы один 3D-объект!")
            return {'CANCELLED'}
            
        scene = context.scene
        original_active = context.view_layer.objects.active
        
        # Шаг 1: Поворачиваем UV каждого меша по гравитации
        for obj in meshes:
            align_mesh_by_gravity(obj, scene)
            
        # Шаг 2: Упаковываем все меши вместе, сохраняя их исходный масштаб
        if scene.pack_after_align:
            pack_uv_islands_keep_scale(meshes, scene, context, original_active)

        # Шаг 3: Настраиваем финальный активный UV-слой и обновляем материалы
        for obj in meshes:
            original_uv_name = obj.gravity_uv_original_name
            if scene.preview_gravity_uv:
                obj.data.uv_layers["Gravity_UV"].active = True
            else:
                if original_uv_name and original_uv_name in obj.data.uv_layers:
                    obj.data.uv_layers[original_uv_name].active = True
            setup_gravity_material(obj, scene)
            
        if original_active:
            context.view_layer.objects.active = original_active
            
        # Принудительно заставляем Блендер обновить вьюпорт окон
        context.area.tag_redraw()
        return {'FINISHED'}
