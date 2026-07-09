import bpy
import math
import os

def get_mix_input(node, name, default_idx):
    socket = node.inputs.get(name)
    if socket:
        return socket
    if default_idx < len(node.inputs):
        return node.inputs[default_idx]
    return None

def get_mix_output(node):
    if len(node.outputs) == 1:
        return node.outputs[0]
    # Для Blender 3.4-3.6 выход Color лежит на индексе 2
    if len(node.outputs) > 2:
        return node.outputs[2]
    return node.outputs[0]

def setup_gravity_material(obj, scene):
    """
    Создает или обновляет временный материал для предпросмотра Gravity_UV на объекте.
    """
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
        
        # Умный выбор канала для шейдера на основе галочки превью
        uv_node = nodes.new(type="ShaderNodeUVMap")
        if scene.preview_gravity_uv:
            uv_node.uv_map = "Gravity_UV"
        else:
            uv_node.uv_map = obj.gravity_uv_original_name if obj.gravity_uv_original_name else ""
        
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
        
        tex_mix_fac = get_mix_input(tex_mix, 'Factor', 0)
        tex_mix_a = get_mix_input(tex_mix, 'A', 6)
        tex_mix_b = get_mix_input(tex_mix, 'B', 7)
        
        if tex_mix_fac:
            tex_mix_fac.default_value = 1.0 if scene.show_debug_arrows else 0.0
        if tex_mix_a:
            links.new(user_tex.outputs['Color'], tex_mix_a)
        if tex_mix_b:
            links.new(arrow_tex.outputs['Color'], tex_mix_b)
        
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
        
        final_mix_fac = get_mix_input(final_mix, 'Factor', 0)
        final_mix_a = get_mix_input(final_mix, 'A', 6)
        final_mix_b = get_mix_input(final_mix, 'B', 7)
        
        if final_mix_a:
            links.new(get_mix_output(tex_mix), final_mix_a)
        if final_mix_b:
            links.new(flat_tex.outputs['Color'], final_mix_b)
        
        if scene.show_flat_highlight:
            try:
                geom = nodes.new(type="ShaderNodeNewGeometry")
                sep = nodes.new(type="ShaderNodeSeparateXYZ")
                math_abs = nodes.new(type="ShaderNodeMath")
                math_abs.operation = 'ABSOLUTE'
                math_comp = nodes.new(type="ShaderNodeMath")
                math_comp.operation = 'GREATER_THAN'
                math_comp.inputs[1].default_value = math.cos(scene.gravity_uv_flat_threshold)
                
                links.new(geom.outputs['Normal'], sep.inputs['Vector'])
                links.new(sep.outputs['Z'], math_abs.inputs[0])
                links.new(math_abs.outputs[0], math_comp.inputs[0])
                if final_mix_fac:
                    links.new(math_comp.outputs[0], final_mix_fac)
            except:
                if final_mix_fac:
                    final_mix_fac.default_value = 0.0
        else:
            if final_mix_fac:
                final_mix_fac.default_value = 0.0
            
        if bsdf:
            links.new(get_mix_output(final_mix), bsdf.inputs['Base Color'])
            
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
