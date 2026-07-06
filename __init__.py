bl_info = {
    "name": "Gravity UV",
    "author": "Твоё Имя & Senior AI",
    "version": (4, 0),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > Gravity UV",
    "description": "Массовое выравнивание UV по гравитации с умной фильтрацией мусора",
    "category": "UV",
}

import bpy
import bmesh
import math
import os
from mathutils import Vector
from collections import defaultdict

# --- СБОРКА МАТЕРИАЛА С КОМБИНИРОВАННЫМИ НАСТРОЙКАМИ (ОБЪЕКТ + СЦЕНА) ---
def setup_gravity_material(obj, scene):
    # Галочки теперь читаются из глобальной сцены (scene), а файл — из объекта (obj)
    need_preview = scene.show_debug_arrows or scene.show_flat_highlight or (obj.gravity_uv_filepath != "")
    mat_name = f"Gravity_Material_{obj.name}"
    
    if need_preview:
        if obj.data.materials and obj.data.materials[0] and not obj.data.materials[0].name.startswith("Gravity_Material_"):
            obj.gravity_uv_cache_mat = obj.data.materials[0].name
            
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(name=mat_name)
            
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        
        try:
            bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
        except:
            bsdf = nodes.new(type="ShaderNodeBsdfPrincipal")
            
        output = nodes.new(type="ShaderNodeOutputMaterial")
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        
        uv_node = nodes.new(type="ShaderNodeUVMap")
        uv_node.uv_map = "Gravity_UV"
        
        mapping_node = nodes.new(type="ShaderNodeMapping")
        mapping_node.inputs['Scale'].default_value = (scene.gravity_uv_scale, scene.gravity_uv_scale, 1.0)
        links.new(uv_node.outputs['UV'], mapping_node.inputs['Vector'])
        
        # 1. Индивидуальная текстура объекта
        user_tex = nodes.new(type="ShaderNodeTexImage")
        if obj.gravity_uv_filepath:
            try:
                img = bpy.data.images.load(obj.gravity_uv_filepath, check_existing=True)
                user_tex.image = img
            except:
                pass
        links.new(mapping_node.outputs['Vector'], user_tex.inputs['Vector'])
                
        # 2. Встроенные стрелки
        arrow_tex = nodes.new(type="ShaderNodeTexImage")
        img_name = "arrows.png"
        embedded_img = bpy.data.images.get(img_name)
        if not embedded_img:
            addon_dir = os.path.dirname(__file__)
            image_path = os.path.join(addon_dir, img_name)
            if os.path.exists(image_path):
                try:
                    embedded_img = bpy.data.images.load(image_path, check_existing=True)
                except:
                    pass
        arrow_tex.image = embedded_img
        links.new(mapping_node.outputs['Vector'], arrow_tex.inputs['Vector'])
                
        tex_mix = nodes.new(type="ShaderNodeMix")
        tex_mix.data_type = 'RGBA'
        tex_mix.inputs[0].default_value = 1.0 if scene.show_debug_arrows else 0.0
        links.new(user_tex.outputs['Color'], tex_mix.inputs[6])
        links.new(arrow_tex.outputs['Color'], tex_mix.inputs[7])
        
        # 3. Встроенные предупреждающие полосы
        flat_tex = nodes.new(type="ShaderNodeTexImage")
        flat_img_name = "flat_warning.png"
        embedded_flat_img = bpy.data.images.get(flat_img_name)
        if not embedded_flat_img:
            addon_dir = os.path.dirname(__file__)
            image_path = os.path.join(addon_dir, flat_img_name)
            if os.path.exists(image_path):
                try:
                    embedded_flat_img = bpy.data.images.load(image_path, check_existing=True)
                except:
                    pass
        flat_tex.image = embedded_flat_img
        links.new(mapping_node.outputs['Vector'], flat_tex.inputs['Vector'])
        
        final_mix = nodes.new(type="ShaderNodeMix")
        final_mix.data_type = 'RGBA'
        links.new(tex_mix.outputs[2], final_mix.inputs[6])
        links.new(flat_tex.outputs['Color'], final_mix.inputs[7])
        
        if scene.show_flat_highlight:
            try:
                geom = nodes.new(type="ShaderNodeNewGeometry")
                sep = nodes.new(type="ShaderNodeSeparateXYZ")
                math_abs = nodes.new(type="ShaderNodeMath")
                math_abs.operation = 'ABSOLUTE'
                math_comp = nodes.new(type="ShaderNodeMath")
                math_comp.operation = 'GREATER_THAN'
                math_comp.inputs[1].default_value = 0.995
                
                links.new(geom.outputs['Normal'], sep.inputs['Vector'])
                links.new(sep.outputs['Z'], math_abs.inputs[0])
                links.new(math_abs.outputs[0], math_comp.inputs[0])
                links.new(math_comp.outputs[0], final_mix.inputs[0])
            except:
                final_mix.inputs[0].default_value = 0.0
        else:
            final_mix.inputs[0].default_value = 0.0
            
        if bsdf:
            links.new(final_mix.outputs[2], bsdf.inputs['Base Color'])
            
        if not obj.data.materials:
            obj.data.materials.append(mat)
        else:
            obj.data.materials[0] = mat
    else:
        if obj.gravity_uv_cache_mat and obj.gravity_uv_cache_mat in bpy.data.materials:
            if obj.data.materials:
                obj.data.materials[0] = bpy.data.materials[obj.gravity_uv_cache_mat]
            else:
                obj.data.materials.append(bpy.data.materials[obj.gravity_uv_cache_mat])
        else:
            if obj.data.materials and obj.data.materials[0] and obj.data.materials[0].name.startswith("Gravity_Material_"):
                obj.data.materials[0] = None

# --- ГЛOБАЛЬНОЕ ОБНОВЛЕНИЕ ВСЕХ ОБЪЕКТОВ СЦЕНЫ ПРИ КЛИКЕ ---
def update_scene_views(self, context):
    # Проходим по абсолютно ВСЕМ объектам сцены
    for obj in context.scene.objects:
        if obj.type == 'MESH' and "Gravity_UV" in obj.data.uv_layers:
            setup_gravity_material(obj, context.scene)

# --- ЛОКАЛЬНОЕ ОБНОВЛЕНИЕ ТОЛЬКО ОДНОГО ОБЪЕКТА (ДЛЯ ПУТИ ТЕКСТУРЫ) ---
def update_object_views(self, context):
    if self.type != 'MESH':
        return
    if "Gravity_UV" in self.data.uv_layers:
        setup_gravity_material(self, context.scene)

# --- ОПЕРАТОР 1: УМНАЯ МАССОВАЯ РАЗВЕРТКА (БЕЗ МУСОРА) ---
class UV_OT_gravity_unwrap(bpy.types.Operator):
    bl_idname = "uv.gravity_unwrap"
    bl_label = "Пересоздать развертку"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # ТВОЯ ИДЕЯ: Фильтруем выделение, берем только полигональные сетки (Mesh)
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

# --- ОПЕРАТОР 2: УМНОЕ МАССОВОЕ ВЫРАВНИВАНИЕ ---
class UV_OT_gravity_align(bpy.types.Operator):
    bl_idname = "uv.gravity_align"
    bl_label = "Выровнять по Гравитации"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # ТВОЯ ИДЕЯ: Полный игнор камер, света и пустышек при массовом нажатии
        meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not meshes:
            self.report({'WARNING'}, "Выделите хотя бы один 3D-объект!")
            return {'CANCELLED'}
            
        scene = context.scene
        original_active = context.view_layer.objects.active
        
        # Цикл массовой автоматической обработки каждого меша по очереди
        for obj in meshes:
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='OBJECT')
            
            original_uv = obj.data.uv_layers.active
            if not original_uv:
                continue
            original_uv_name = original_uv.name
            
            gravity_uv_name = "Gravity_UV"
            gravity_uv = obj.data.uv_layers.get(gravity_uv_name)
            if not gravity_uv:
                gravity_uv = obj.data.uv_layers.new(name=gravity_uv_name)
                
            bpy.ops.object.mode_set(mode='EDIT')
            
            matrix_world = obj.matrix_world.to_3x3()
            gravity = Vector((0, 0, -1))
            
            bm = bmesh.from_edit_mesh(obj.data)
            uv_original_layer = bm.loops.layers.uv[original_uv_name]
            uv_gravity_layer = bm.loops.layers.uv[gravity_uv_name]
            
            # Копируем структуру развертки
            for face in bm.faces:
                for loop in face.loops:
                    loop[uv_gravity_layer].uv = loop[uv_original_layer].uv.copy()
                    
            # Твоя группировка по плоскостям для идеального склеивания без зигзагов
            normal_groups = defaultdict(list)
            for face in bm.faces:
                if len(face.loops) < 3:
                    continue
                world_normal = (matrix_world @ face.normal).normalized()
                key = (round(world_normal.x, 4), round(world_normal.y, 4), round(world_normal.z, 4))
                normal_groups[key].append(face)
                
            for normal_key, faces in normal_groups.items():
                is_flat = abs(normal_key[2]) > 0.995
                
                if is_flat:
                    if scene.flat_faces_mode == 'IGNORE':
                        continue
                    else:
                        angle = scene.flat_faces_angle
                else:
                    angle = None
                    for face in faces:
                        l0, l1, l2 = face.loops[0], face.loops[1], face.loops[2]
                        p0, p1, p2 = l0.vert.co, l1.vert.co, l2.vert.co
                        uv0, uv1, uv2 = l0[uv_gravity_layer].uv, l1[uv_gravity_layer].uv, l2[uv_gravity_layer].uv
                        
                        edge1 = p1 - p0
                        edge2 = p2 - p0
                        duv1 = uv1 - uv0
                        duv2 = uv2 - uv0
                        
                        det = duv1.x * duv2.y - duv2.x * duv1.y
                        if abs(det) < 1e-6:
                            continue
                            
                        inv_det = 1.0 / det
                        tangent = (edge1 * duv2.y - edge2 * duv1.y) * inv_det
                        bitangent = (edge2 * duv1.x - edge1 * duv2.x) * inv_det
                        
                        world_tangent = (matrix_world @ tangent).normalized()
                        world_bitangent = (matrix_world @ bitangent).normalized()
                        
                        u_gravity = gravity.dot(world_tangent)
                        v_gravity = gravity.dot(world_bitangent)
                        
                        angle = math.atan2(u_gravity, v_gravity)
                        break
                        
                    if angle is None:
                        continue
                        
                all_loops = [l for f in faces for l in f.loops]
                if not all_loops:
                    continue
                    
                center_u = sum(l[uv_gravity_layer].uv.x for l in all_loops) / len(all_loops)
                center_v = sum(l[uv_gravity_layer].uv.y for l in all_loops) / len(all_loops)
                
                cos_a = math.cos(angle)
                sin_a = math.sin(angle)
                
                for l in all_loops:
                    uv = l[uv_gravity_layer].uv
                    u_shifted = uv.x - center_u
                    v_shifted = uv.y - center_v
                    
                    uv.x = center_u + (u_shifted * cos_a - v_shifted * sin_a)
                    uv.y = center_v + (u_shifted * sin_a + v_shifted * cos_a)
                    
            bmesh.update_edit_mesh(obj.data)
            bpy.ops.object.mode_set(mode='OBJECT')
            
            obj.data.uv_layers[original_uv_name].active = True
            setup_gravity_material(obj, scene)
            
        # Восстанавливаем активный объект в конце
        if original_active:
            context.view_layer.objects.active = original_active
        return {'FINISHED'}

# --- ИНТЕРФЕЙСНАЯ ПАНЕЛЬ С УМНЫМ РАЗДЕЛЕНИЕМ (ОБЪЕКТ / СЦЕНА) ---
class UV_PT_gravity_panel(bpy.types.Panel):
    bl_label = "Gravity UV"
    bl_idname = "UV_PT_gravity_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Gravity UV"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = context.active_object
        
        # Если ничего не выделено — вежливо просим сделать выбор
        if not obj or obj.type != 'MESH':
            layout.label(text="Выберите полигональный объект", icon='ERROR')
            return
            
        box_prep = layout.box()
        box_prep.label(text="1. Подготовка (Поддерживает Batch):", icon='MESH_DATA')
        box_prep.operator("uv.gravity_unwrap", text="Пересоздать развертку", icon='UV_DATA')
        
        box_action = layout.box()
        box_action.label(text="2. Выравнивание (Поддерживает Batch):", icon='WORLD_DATA')
        box_action.operator("uv.gravity_align", text="Выровнять по Гравитации", icon='OBJECT_DATA')
        
        box_tex = layout.box()
        box_tex.label(text="3. Управление текстурами:", icon='IMAGE_DATA')
        # Индивидуальное свойство (у каждого объекта своя текстура)
        box_tex.prop(obj, "gravity_uv_filepath", text="")
        # Глобальные свойства сцены (включаются сразу для всех объектов!)
        box_tex.prop(scene, "show_debug_arrows", text="Включить тестовые стрелки")
        box_tex.prop(scene, "gravity_uv_scale", text="Масштаб (тайлинг)")
        
        box_flat = layout.box()
        box_flat.label(text="4. Настройки плоских граней:", icon='COLOR')
        # Глобальное свойство сцены
        box_flat.prop(scene, "show_flat_highlight", text="Разметка плоских граней (Текстура)")
        box_flat.prop(scene, "flat_faces_mode", text="Обработка")
        if scene.flat_faces_mode == 'ALIGN':
            box_flat.prop(scene, "flat_faces_angle", text="Угол поворота")

# --- РЕГИСТРАЦИЯ НАСТРОЕК ---
def register():
    # Локальная память объектов (Текстуры и кэш)
    bpy.types.Object.gravity_uv_cache_mat = bpy.props.StringProperty(name="Cached Material", default="")
    bpy.types.Object.gravity_uv_filepath = bpy.props.StringProperty(
        name="Файл текстуры", subtype='FILE_PATH', update=update_object_views
    )
    
    # Глобальная память сцены (Синхронные галочки вьюпорта)
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
    
    bpy.utils.register_class(UV_OT_gravity_unwrap)
    bpy.utils.register_class(UV_OT_gravity_align)
    bpy.utils.register_class(UV_PT_gravity_panel)

def unregister():
    bpy.utils.unregister_class(UV_OT_gravity_unwrap)
    bpy.utils.unregister_class(UV_OT_gravity_align)
    bpy.utils.unregister_class(UV_PT_gravity_panel)
    del bpy.types.Object.gravity_uv_cache_mat
    del bpy.types.Object.gravity_uv_filepath
    del bpy.types.Scene.show_debug_arrows
    del bpy.types.Scene.show_flat_highlight
    del bpy.types.Scene.gravity_uv_scale
    del bpy.types.Scene.flat_faces_mode
    del bpy.types.Scene.flat_faces_angle

if __name__ == "__main__":
    register()