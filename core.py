import bpy
import bmesh
import math
from mathutils import Vector
from collections import defaultdict

def align_mesh_by_gravity(obj, scene):
    """
    Выравнивает UV-развертку меша по вектору гравитации (0, 0, -1).
    Полигоны группируются по сонаправленности нормалей с погрешностью coplanar_threshold.
    """
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Если у объекта вообще нет разверток — создаем дефолтную
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
        
    original_uv = obj.data.uv_layers.active
    if original_uv.name != "Gravity_UV":
        obj.gravity_uv_original_name = original_uv.name
        
    original_uv_name = obj.gravity_uv_original_name
    
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
    
    # Копируем 1 в 1 для сохранения размеров
    for face in bm.faces:
        for loop in face.loops:
            loop[uv_gravity_layer].uv = loop[uv_original_layer].uv.copy()
            
    if obj.gravity_uv_use_local_coplanar:
        coplanar_threshold = obj.gravity_uv_local_coplanar_threshold
    else:
        coplanar_threshold = scene.gravity_uv_coplanar_threshold
    flat_threshold_cos = math.cos(scene.gravity_uv_flat_threshold)
    
    normal_groups = []  # Список кортежей: (group_normal, [faces])
    for face in bm.faces:
        if len(face.loops) < 3:
            continue
        world_normal = (matrix_world @ face.normal).normalized()
        
        # Ищем группу с близкой нормалью
        found = False
        for group_normal, group_faces in normal_groups:
            dot = world_normal.dot(group_normal)
            dot = max(-1.0, min(1.0, dot))
            angle_diff = math.acos(dot)
            if angle_diff <= coplanar_threshold:
                group_faces.append(face)
                found = True
                break
        if not found:
            normal_groups.append((world_normal, [face]))
        
    for group_normal, faces in normal_groups:
        is_flat = abs(group_normal.z) >= flat_threshold_cos
        
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
        
        # Поворачиваем группу без изменения размеров
        for l in all_loops:
            uv = l[uv_gravity_layer].uv
            u_shifted = uv.x - center_u
            v_shifted = uv.y - center_v
            
            uv.x = center_u + (u_shifted * cos_a - v_shifted * sin_a)
            uv.y = center_v + (u_shifted * sin_a + v_shifted * cos_a)
            
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')

def pack_uv_islands_keep_scale(meshes, scene, context, original_active):
    """
    Упаковывает UV-островки всех выделенных мешей вместе без изменения масштаба.
    """
    # Делаем активным любой из мешей, чтобы войти в режим редактирования
    if original_active in meshes:
        context.view_layer.objects.active = original_active
    else:
        context.view_layer.objects.active = meshes[0]
        
    bpy.ops.object.mode_set(mode='EDIT')
    
    # Делаем "Gravity_UV" активной картой во всех мешах для редактирования
    for obj in meshes:
        obj.data.uv_layers.active = obj.data.uv_layers["Gravity_UV"]
        
    # Ищем две точки на UV для замера масштаба до упаковки
    ref_data = None
    for obj in meshes:
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.get("Gravity_UV")
        if not uv_layer:
            continue
        for face in bm.faces:
            if len(face.loops) >= 2:
                uv1 = face.loops[0][uv_layer].uv.copy()
                uv2 = face.loops[1][uv_layer].uv.copy()
                dist = (uv2 - uv1).length
                if dist > 0.0001:
                    ref_data = {
                        'obj_name': obj.name,
                        'face_index': face.index,
                        'dist_old': dist
                    }
                    break
        if ref_data:
            break
    
    # Выделяем все UV координаты во всех мешах
    bpy.ops.uv.select_all(action='SELECT')
    
    # Вызываем встроенный упаковщик (вращение выключено)
    bpy.ops.uv.pack_islands(rotate=False, margin=0.01)
    
    # Восстанавливаем масштаб, если он изменился
    if ref_data:
        ref_obj = bpy.data.objects.get(ref_data['obj_name'])
        if ref_obj:
            bm_ref = bmesh.from_edit_mesh(ref_obj.data)
            uv_layer_ref = bm_ref.loops.layers.uv.get("Gravity_UV")
            bm_ref.faces.ensure_lookup_table()
            face = bm_ref.faces[ref_data['face_index']]
            uv1 = face.loops[0][uv_layer_ref].uv
            uv2 = face.loops[1][uv_layer_ref].uv
            dist_new = (uv2 - uv1).length
            
            if dist_new > 0.00001:
                scale_factor = dist_new / ref_data['dist_old']
                if abs(scale_factor - 1.0) > 0.0001:
                    inv_scale = 1.0 / scale_factor
                    for o in meshes:
                        bm_o = bmesh.from_edit_mesh(o.data)
                        uv_lay = bm_o.loops.layers.uv.get("Gravity_UV")
                        for f in bm_o.faces:
                            for l in f.loops:
                                l[uv_lay].uv *= inv_scale
                        bmesh.update_edit_mesh(o.data)
                        
    # Выходим из Edit Mode
    bpy.ops.object.mode_set(mode='OBJECT')
