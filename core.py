import bpy
import bmesh
import math
import numpy as np
from mathutils import Vector

# Глобальный реестр кэша в оперативной памяти сессии Blender
_gravity_uv_cache = {}

class GravityUVCache:
    """
    Класс для хранения кэшированных геометрических и UV данных объекта.
    Позволяет интерактивному решателю работать на C-уровне без обращений к API Blender.
    """
    def __init__(self, uv_orig, loop_island_ids, num_islands, island_centers, loop_to_poly,
                 poly_normals, poly_tangents, poly_bitangents,
                 island_normals, island_tangents, island_bitangents):
        self.uv_orig = uv_orig  # np.ndarray [L, 2] (исходная развертка)
        self.loop_island_ids = loop_island_ids  # np.ndarray [L] (ID острова для каждого лупа)
        self.num_islands = num_islands  # int (количество островов)
        self.island_centers = island_centers  # np.ndarray [num_islands, 2] (центры островов)
        self.loop_to_poly = loop_to_poly  # np.ndarray [L] (сопоставление лупа к полигону)
        
        # Направления для работы по плоскостям (COPLANAR)
        self.poly_normals = poly_normals  # np.ndarray [P, 3]
        self.poly_tangents = poly_tangents  # np.ndarray [P, 3]
        self.poly_bitangents = poly_bitangents  # np.ndarray [P, 3]
        
        # Усредненные направления для работы целыми островами (ISLANDS)
        self.island_normals = island_normals  # np.ndarray [num_islands, 3]
        self.island_tangents = island_tangents  # np.ndarray [num_islands, 3]
        self.island_bitangents = island_bitangents  # np.ndarray [num_islands, 3]


def clear_gravity_uv_cache(obj):
    """Удаляет кэш объекта из памяти."""
    ptr = obj.as_pointer()
    if ptr in _gravity_uv_cache:
        del _gravity_uv_cache[ptr]


def get_gravity_uv_cache(obj):
    """Получает кэш объекта из памяти."""
    return _gravity_uv_cache.get(obj.as_pointer())


def find_uv_islands_numpy_internal(obj, scene, uv_layer, use_coplanar, coplanar_threshold, vertex_indices, uv_coords,
                                   split_on_twist=False, twist_threshold=1.0471975,
                                   poly_gravity_angles=None, poly_gravity_mag=None):
    """
    Быстрый BFS-алгоритм для поиска UV-островов (компонент связности) на чистом Python + NumPy.
    Разбивает граф по плоскостям, если включен режим COPLANAR или контроль закручивания.
    """
    mesh = obj.data
    num_loops = len(mesh.loops)
    num_polys = len(mesh.polygons)
    
    # Округляем UV координаты для компенсации погрешностей с плавающей запятой
    uv_rounded = np.round(uv_coords, decimals=5)
    
    # Строим уникальные ключи для определения UV-вершин
    keys = np.empty((num_loops, 3), dtype=np.float64)
    keys[:, 0] = vertex_indices
    keys[:, 1:] = uv_rounded.reshape(num_loops, 2)
    
    _, uv_vertex_ids = np.unique(keys, axis=0, return_inverse=True)
    num_uv_verts = np.max(uv_vertex_ids) + 1 if len(uv_vertex_ids) > 0 else 0
    
    # Строим карту loop_to_poly
    poly_loop_totals = np.empty(num_polys, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", poly_loop_totals)
    loop_to_poly = np.repeat(np.arange(num_polys, dtype=np.int32), poly_loop_totals)
    
    # Двудольный граф смежности: UV-вершины <-> Полигоны
    uv_to_polys = [[] for _ in range(num_uv_verts)]
    poly_to_uv_verts = [[] for _ in range(num_polys)]
    
    for loop_idx in range(num_loops):
        poly_idx = loop_to_poly[loop_idx]
        uv_vert_id = uv_vertex_ids[loop_idx]
        uv_to_polys[uv_vert_id].append(poly_idx)
        poly_to_uv_verts[poly_idx].append(uv_vert_id)
        
    poly_visited = np.zeros(num_polys, dtype=bool)
    uv_vert_visited = np.zeros(num_uv_verts, dtype=bool)
    poly_island_ids = np.full(num_polys, -1, dtype=np.int32)
    island_counter = 0
    
    if use_coplanar or split_on_twist:
        # Вычисляем мировые нормали для проверки сонаправленности
        poly_normals = np.empty(num_polys * 3, dtype=np.float32)
        mesh.polygons.foreach_get("normal", poly_normals)
        poly_normals.shape = (num_polys, 3)
        
        matrix_world = np.array(obj.matrix_world.to_3x3(), dtype=np.float32)
        world_normals = poly_normals @ matrix_world.T
        wn_len = np.linalg.norm(world_normals, axis=1, keepdims=True)
        wn_len[wn_len < 1e-6] = 1.0
        world_normals /= wn_len
        
        # Определяем горизонтальные полигоны (крыша / пол)
        flat_threshold_cos = math.cos(scene.gravity_uv_flat_threshold)
        is_flat = np.abs(world_normals[:, 2]) >= flat_threshold_cos
        
        # Готовим 2D проекции нормалей на XY плоскость
        use_xy_projection = scene.gravity_uv_use_xy_projection
        if use_xy_projection:
            xy_normals = world_normals[:, :2].copy()
            xy_len = np.linalg.norm(xy_normals, axis=1, keepdims=True)
            xy_len[xy_len < 1e-5] = 1.0
            xy_normals /= xy_len
            
        # Выгружаем координаты вершин для пространственной сортировки полигонов
        vertices_co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", vertices_co)
        vertices_co.shape = (len(mesh.vertices), 3)
        
        poly_loop_starts = np.empty(num_polys, dtype=np.int32)
        mesh.polygons.foreach_get("loop_start", poly_loop_starts)
        poly_first_v_indices = vertex_indices[poly_loop_starts]
        poly_centers = vertices_co[poly_first_v_indices]
        
        # Сортируем индексы полигонов:
        # 1. По высоте Z (от верхних к нижним)
        # 2. По Y
        # 3. По абсолютному X (чтобы симметричные стороны обрабатывались одинаково от центра к краям)
        sorted_poly_indices = np.lexsort((
            np.abs(poly_centers[:, 0]),  # abs(X)
            poly_centers[:, 1],           # Y
            -poly_centers[:, 2]          # -Z (высота)
        ))
            
        # BFS с проверкой нормалей и закручивания гравитации
        for start_poly in sorted_poly_indices:
            if poly_visited[start_poly]:
                continue
                
            queue = [start_poly]
            poly_visited[start_poly] = True
            poly_island_ids[start_poly] = island_counter
            
            # Угол гравитации стартового полигона для проверки закручивания
            seed_angle = poly_gravity_angles[start_poly] if poly_gravity_angles is not None else 0.0
            
            head = 0
            while head < len(queue):
                curr_poly = queue[head]
                head += 1
                curr_normal = world_normals[curr_poly]
                curr_is_flat = is_flat[curr_poly]
                
                for uv_vert in poly_to_uv_verts[curr_poly]:
                    for neighbor_poly in uv_to_polys[uv_vert]:
                        if not poly_visited[neighbor_poly]:
                            neighbor_is_flat = is_flat[neighbor_poly]
                            
                            # Не соединяем горизонтальные грани со стенами
                            if curr_is_flat != neighbor_is_flat:
                                continue
                                
                            if curr_is_flat:
                                # Горизонтальные полигоны объединяем в один остров
                                poly_visited[neighbor_poly] = True
                                poly_island_ids[neighbor_poly] = island_counter
                                queue.append(neighbor_poly)
                            else:
                                # Наклонные грани
                                
                                # 1. Контроль резких изломов (по нормалям), только если включен use_coplanar
                                if use_coplanar:
                                    if use_xy_projection:
                                        curr_xy = xy_normals[curr_poly]
                                        neigh_xy = xy_normals[neighbor_poly]
                                        dot = curr_xy[0]*neigh_xy[0] + curr_xy[1]*neigh_xy[1]
                                        dot = max(-1.0, min(1.0, dot))
                                        angle_diff = math.acos(dot)
                                    else:
                                        neighbor_normal = world_normals[neighbor_poly]
                                        dot = curr_normal[0]*neighbor_normal[0] + curr_normal[1]*neighbor_normal[1] + curr_normal[2]*neighbor_normal[2]
                                        dot = max(-1.0, min(1.0, dot))
                                        angle_diff = math.acos(dot)
                                        
                                    if angle_diff > coplanar_threshold:
                                        continue  # Делаем разрез
                                
                                # 2. Контроль закручивания гравитации
                                if split_on_twist and poly_gravity_angles is not None:
                                    # Проверяем только если проекция гравитации достаточно сильная
                                    # (чтобы не резать из-за погрешностей на почти плоских горизонтальных фейсах)
                                    if poly_gravity_mag[neighbor_poly] > 0.05 and poly_gravity_mag[start_poly] > 0.05:
                                        neigh_angle = poly_gravity_angles[neighbor_poly]
                                        # Разница углов с учетом циклического сдвига [-pi, pi]
                                        diff = abs((neigh_angle - seed_angle + math.pi) % (2 * math.pi) - math.pi)
                                        if diff > twist_threshold:
                                            continue  # Делаем разрез
                                            
                                poly_visited[neighbor_poly] = True
                                poly_island_ids[neighbor_poly] = island_counter
                                queue.append(neighbor_poly)
            island_counter += 1
    else:
        # Обычный BFS (быстрый)
        for start_poly in range(num_polys):
            if poly_visited[start_poly]:
                continue
                
            queue = [start_poly]
            poly_visited[start_poly] = True
            poly_island_ids[start_poly] = island_counter
            
            head = 0
            while head < len(queue):
                curr_poly = queue[head]
                head += 1
                
                for uv_vert in poly_to_uv_verts[curr_poly]:
                    if not uv_vert_visited[uv_vert]:
                        uv_vert_visited[uv_vert] = True
                        for neighbor_poly in uv_to_polys[uv_vert]:
                            if not poly_visited[neighbor_poly]:
                                poly_visited[neighbor_poly] = True
                                poly_island_ids[neighbor_poly] = island_counter
                                queue.append(neighbor_poly)
            island_counter += 1
            
    loop_island_ids = poly_island_ids[loop_to_poly]
    return loop_island_ids, island_counter


def build_gravity_uv_cache(obj, scene):
    """
    Фаза А: Движок Кэширования (Static Cache Engine).
    Выгружает геометрию через foreach_get, вычисляет тангенсы/нормали/центроиды
    и строит NumPy структуру кэша в памяти.
    """
    if not obj or obj.type != 'MESH':
        return None
        
    import time
    t_start = time.perf_counter()
    
    prev_mode = obj.mode
    if prev_mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except:
            pass

    def safe_return(result):
        if prev_mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode=prev_mode)
            except:
                pass
        return result
        
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="UVMap")
        
    original_uv = mesh.uv_layers.active
    if original_uv.name == "Gravity_UV":
        # Восстанавливаем оригинальную карту из кэша объекта
        orig_name = obj.gravity_uv_original_name
        original_uv = mesh.uv_layers.get(orig_name) if orig_name else None
        if not original_uv:
            for layer in mesh.uv_layers:
                if layer.name != "Gravity_UV":
                    original_uv = layer
                    break
        if not original_uv:
            return safe_return(None)
    else:
        obj.gravity_uv_original_name = original_uv.name
        
    # Инициализируем Gravity_UV
    gravity_uv = mesh.uv_layers.get("Gravity_UV")
    if not gravity_uv:
        gravity_uv = mesh.uv_layers.new(name="Gravity_UV")
        
    num_loops = len(mesh.loops)
    num_polys = len(mesh.polygons)
    if num_loops == 0 or num_polys == 0:
        return safe_return(None)
        
    # Выгружаем оригинальные UV
    uv_orig = np.empty(num_loops * 2, dtype=np.float32)
    original_uv.data.foreach_get("uv", uv_orig)
    uv_orig.shape = (num_loops, 2)
    
    # Выгружаем индексы вершин
    vertex_indices = np.empty(num_loops, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", vertex_indices)
    
    # Препроцессинг геометрических данных (нормали, тангенсы, битангенсы)
    # Loop to Poly
    poly_loop_totals = np.empty(num_polys, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", poly_loop_totals)
    loop_to_poly = np.repeat(np.arange(num_polys, dtype=np.int32), poly_loop_totals)
    
    # Нормали полигонов
    poly_normals = np.empty(num_polys * 3, dtype=np.float32)
    mesh.polygons.foreach_get("normal", poly_normals)
    poly_normals.shape = (num_polys, 3)
    
    matrix_world = np.array(obj.matrix_world.to_3x3(), dtype=np.float32)
    world_normals = poly_normals @ matrix_world.T
    wn_len = np.linalg.norm(world_normals, axis=1, keepdims=True)
    wn_len[wn_len < 1e-6] = 1.0
    world_normals /= wn_len
    
    # Тангенсы и битангенсы
    poly_loop_starts = np.empty(num_polys, dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", poly_loop_starts)
    
    v0_indices = vertex_indices[poly_loop_starts]
    v1_indices = vertex_indices[poly_loop_starts + 1]
    v2_indices = vertex_indices[poly_loop_starts + 2]
    
    vertices_co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", vertices_co)
    vertices_co.shape = (len(mesh.vertices), 3)
    
    p0 = vertices_co[v0_indices]
    p1 = vertices_co[v1_indices]
    p2 = vertices_co[v2_indices]
    
    uv0 = uv_orig[poly_loop_starts]
    uv1 = uv_orig[poly_loop_starts + 1]
    uv2 = uv_orig[poly_loop_starts + 2]
    
    edge1 = p1 - p0
    edge2 = p2 - p0
    duv1 = uv1 - uv0
    duv2 = uv2 - uv0
    
    det = duv1[:, 0] * duv2[:, 1] - duv2[:, 0] * duv1[:, 1]
    det[np.abs(det) < 1e-6] = 1e-6
    inv_det = 1.0 / det
    
    tangent = (edge1 * duv2[:, 1][:, np.newaxis] - edge2 * duv1[:, 1][:, np.newaxis]) * inv_det[:, np.newaxis]
    bitangent = (edge2 * duv1[:, 0][:, np.newaxis] - edge1 * duv2[:, 0][:, np.newaxis]) * inv_det[:, np.newaxis]
    
    world_tangents = tangent @ matrix_world.T
    wt_len = np.linalg.norm(world_tangents, axis=1, keepdims=True)
    wt_len[wt_len < 1e-6] = 1.0
    world_tangents /= wt_len
    
    world_bitangents = bitangent @ matrix_world.T
    wb_len = np.linalg.norm(world_bitangents, axis=1, keepdims=True)
    wb_len[wb_len < 1e-6] = 1.0
    world_bitangents /= wb_len

    # Определяем порог искривления нормалей
    if obj.gravity_uv_use_local_coplanar:
        coplanar_threshold = obj.gravity_uv_local_coplanar_threshold
    else:
        coplanar_threshold = scene.gravity_uv_coplanar_threshold
        
    use_coplanar = (scene.gravity_uv_rotation_mode == 'COPLANAR')
    
    # Препрессинг углов гравитации для контроля закручивания
    split_on_twist = scene.gravity_uv_split_on_twist
    twist_threshold = scene.gravity_uv_twist_threshold
    poly_gravity_angles = None
    poly_gravity_mag = None
    
    if split_on_twist:
        gravity_vec = Vector((scene.gravity_uv_direction_x, scene.gravity_uv_direction_y, scene.gravity_uv_direction_z))
        if gravity_vec.length > 0.0001:
            gravity_vec.normalize()
        else:
            gravity_vec = Vector((0.0, 0.0, -1.0))
        G = np.array(gravity_vec, dtype=np.float32)
        u_grav = np.sum(G * world_tangents, axis=1)
        v_grav = np.sum(G * world_bitangents, axis=1)
        poly_gravity_angles = np.arctan2(u_grav, v_grav)
        poly_gravity_mag = np.sqrt(u_grav**2 + v_grav**2)

    # Находим острова
    loop_island_ids, num_islands = find_uv_islands_numpy_internal(
        obj, scene, original_uv, use_coplanar, coplanar_threshold, vertex_indices, uv_orig,
        split_on_twist=split_on_twist, twist_threshold=twist_threshold,
        poly_gravity_angles=poly_gravity_angles, poly_gravity_mag=poly_gravity_mag
    )
    
    # Вычисляем центроиды UV-островов
    island_uv_sums = np.zeros((num_islands, 2), dtype=np.float32)
    np.add.at(island_uv_sums, loop_island_ids, uv_orig)
    island_loop_counts = np.zeros(num_islands, dtype=np.float32)
    np.add.at(island_loop_counts, loop_island_ids, 1.0)
    island_loop_counts[island_loop_counts < 1.0] = 1.0
    island_centers = island_uv_sums / island_loop_counts[:, np.newaxis]
    
    # Усредняем направления по островам
    island_tangents = np.zeros((num_islands, 3), dtype=np.float32)
    np.add.at(island_tangents, loop_island_ids, world_tangents[loop_to_poly])
    it_len = np.linalg.norm(island_tangents, axis=1, keepdims=True)
    it_len[it_len < 1e-6] = 1.0
    island_tangents /= it_len
    
    island_bitangents = np.zeros((num_islands, 3), dtype=np.float32)
    np.add.at(island_bitangents, loop_island_ids, world_bitangents[loop_to_poly])
    ib_len = np.linalg.norm(island_bitangents, axis=1, keepdims=True)
    ib_len[ib_len < 1e-6] = 1.0
    island_bitangents /= ib_len
    
    island_normals = np.zeros((num_islands, 3), dtype=np.float32)
    np.add.at(island_normals, loop_island_ids, world_normals[loop_to_poly])
    in_len = np.linalg.norm(island_normals, axis=1, keepdims=True)
    in_len[in_len < 1e-6] = 1.0
    island_normals /= in_len
    
    cache = GravityUVCache(
        uv_orig=uv_orig,
        loop_island_ids=loop_island_ids,
        num_islands=num_islands,
        island_centers=island_centers,
        loop_to_poly=loop_to_poly,
        poly_normals=world_normals,
        poly_tangents=world_tangents,
        poly_bitangents=world_bitangents,
        island_normals=island_normals,
        island_tangents=island_tangents,
        island_bitangents=island_bitangents
    )
    
    _gravity_uv_cache[obj.as_pointer()] = cache
    return safe_return(cache)


def solve_gravity_uv(obj, scene):
    """
    Фаза Б: Интерактивный Динамический Решатель (Dynamic Execution Solver).
    Быстрый матричный расчет поворота UV-островов по гравитации на C-уровне NumPy.
    Вызывается автоматически при движении ползунков.
    """
    import time
    t_start = time.perf_counter()
    
    cache = get_gravity_uv_cache(obj)
    if not cache:
        cache = build_gravity_uv_cache(obj, scene)
        if not cache:
            return
            
    # Вычисляем 3D вектор направления потеков
    gravity_vec = Vector((scene.gravity_uv_direction_x, scene.gravity_uv_direction_y, scene.gravity_uv_direction_z))
    if gravity_vec.length > 0.0001:
        gravity_vec.normalize()
    else:
        gravity_vec = Vector((0.0, 0.0, -1.0))
        
    G = np.array(gravity_vec, dtype=np.float32)
    
    # Погрешность горизонтали
    flat_threshold_cos = math.cos(scene.gravity_uv_flat_threshold)
    
    # Проверка на горизонтальность (крыша / пол)
    is_flat = np.abs(cache.island_normals[:, 2]) >= flat_threshold_cos
    
    # Проецируем гравитацию на тангенс и битангенс островов
    u_grav = np.sum(G * cache.island_tangents, axis=1)
    v_grav = np.sum(G * cache.island_bitangents, axis=1)
    
    # Рассчитываем углы поворота
    angles = np.arctan2(u_grav, v_grav)
    

    
    # Настройки для плоских граней
    if scene.flat_faces_mode == 'IGNORE':
        angles[is_flat] = 0.0
    else:
        angles[is_flat] = scene.flat_faces_angle
        
    # Распределяем углы на лупы
    loop_angles = angles[cache.loop_island_ids]
    
    cos_a = np.cos(loop_angles)
    sin_a = np.sin(loop_angles)
    
    # Центры вращения для лупов
    loop_centers = cache.island_centers[cache.loop_island_ids]
    
    # Матричный поворот координат
    u_shifted = cache.uv_orig[:, 0] - loop_centers[:, 0]
    v_shifted = cache.uv_orig[:, 1] - loop_centers[:, 1]
    
    uv_new = np.empty_like(cache.uv_orig)
    uv_new[:, 0] = loop_centers[:, 0] + (u_shifted * cos_a - v_shifted * sin_a)
    uv_new[:, 1] = loop_centers[:, 1] + (u_shifted * sin_a + v_shifted * cos_a)
    
    # Запись обратно в меш Blender
    mesh = obj.data
    gravity_uv = mesh.uv_layers.get("Gravity_UV")
    if gravity_uv:
        prev_mode = obj.mode
        t_mode_switch = 0.0
        
        # Переключение в Object Mode для записи в меш
        if prev_mode == 'EDIT':
            t_m0 = time.perf_counter()
            bpy.ops.object.mode_set(mode='OBJECT')
            t_mode_switch += (time.perf_counter() - t_m0)
            
        gravity_uv.data.foreach_set("uv", uv_new.ravel())
        mesh.update()
        
        # Возврат в Edit Mode, если мы из него вышли
        if prev_mode == 'EDIT':
            t_m1 = time.perf_counter()
            bpy.ops.object.mode_set(mode='EDIT')
            t_mode_switch += (time.perf_counter() - t_m1)
            
        # Локальный тайминг не требуется, пишется суммарный
        pass


def align_mesh_by_gravity(obj, scene):
    """
    Запуск Фазы А (кэширование) и последующий расчет Фазы Б.
    """
    # Сбрасываем старый кэш, чтобы гарантированно пересчитать геометрию
    clear_gravity_uv_cache(obj)
    
    # Строим кэш
    cache = build_gravity_uv_cache(obj, scene)
    if cache:
        # Вызываем решатель для расчета исходной развертки по гравитации
        solve_gravity_uv(obj, scene)


def pack_uv_islands_keep_scale(meshes, scene, context, original_active):
    """
    Упаковывает UV-островки всех выделенных мешей вместе без изменения масштаба,
    после чего обновляет кэш (сохраняет новые упакованные координаты в uv_orig).
    Работает через стабильный Object Mode и NumPy для исключения багов кэширования bmesh.
    """
    if not meshes:
        return
        
    # Шаг 1: Замеряем исходный масштаб в Object Mode (до входа в Edit Mode)
    ref_data = None
    for obj in meshes:
        gravity_uv = obj.data.uv_layers.get("Gravity_UV")
        if not gravity_uv:
            continue
        for poly in obj.data.polygons:
            if len(poly.loop_indices) >= 2:
                l1 = poly.loop_indices[0]
                l2 = poly.loop_indices[1]
                uv1 = Vector(gravity_uv.data[l1].uv)
                uv2 = Vector(gravity_uv.data[l2].uv)
                dist = (uv2 - uv1).length
                if dist > 0.0001:
                    ref_data = {
                        'obj_name': obj.name,
                        'loop_indices': (l1, l2),
                        'dist_old': dist
                    }
                    break
        if ref_data:
            break
            
    # Шаг 2: Входим в Edit Mode для выполнения упаковки
    if original_active in meshes:
        context.view_layer.objects.active = original_active
    else:
        context.view_layer.objects.active = meshes[0]
        
    bpy.ops.object.mode_set(mode='EDIT')
    
    for obj in meshes:
        obj.data.uv_layers.active = obj.data.uv_layers["Gravity_UV"]
        
    bpy.ops.uv.select_all(action='SELECT')
    # Упаковываем без изменения относительного масштаба островков и с фиксированным UV-отступом
    try:
        bpy.ops.uv.pack_islands(rotate=False, scale=False, margin_method='ADD', margin=0.01)
    except TypeError:
        # Резервный вариант для старых версий Blender, где нет margin_method
        bpy.ops.uv.pack_islands(rotate=False, scale=False, margin=0.01)
    
    # Шаг 3: Выходим в Object Mode для гарантированного обновления данных меша
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Шаг 4: Замеряем новый масштаб в Object Mode и восстанавливаем его через NumPy
    if ref_data:
        ref_obj = bpy.data.objects.get(ref_data['obj_name'])
        if ref_obj:
            gravity_uv = ref_obj.data.uv_layers.get("Gravity_UV")
            l1, l2 = ref_data['loop_indices']
            uv1 = Vector(gravity_uv.data[l1].uv)
            uv2 = Vector(gravity_uv.data[l2].uv)
            dist_new = (uv2 - uv1).length
            
            if dist_new > 0.00001:
                scale_factor = dist_new / ref_data['dist_old']
                if abs(scale_factor - 1.0) > 0.0001:
                    inv_scale = 1.0 / scale_factor
                    for o in meshes:
                        gov = o.data.uv_layers.get("Gravity_UV")
                        if gov:
                            num_loops = len(o.data.loops)
                            uvs = np.empty(num_loops * 2, dtype=np.float32)
                            gov.data.foreach_get("uv", uvs)
                            uvs *= inv_scale
                            gov.data.foreach_set("uv", uvs)
                            o.data.update()
                            
    # Шаг 5: Обновляем кэш оригинальных координат в памяти
    for obj in meshes:
        cache = get_gravity_uv_cache(obj)
        if cache:
            num_loops = len(obj.data.loops)
            uv_packed = np.empty(num_loops * 2, dtype=np.float32)
            obj.data.uv_layers["Gravity_UV"].data.foreach_get("uv", uv_packed)
            uv_packed.shape = (num_loops, 2)
            
            cache.uv_orig = uv_packed
            
            island_uv_sums = np.zeros((cache.num_islands, 2), dtype=np.float32)
            np.add.at(island_uv_sums, cache.loop_island_ids, uv_packed)
            island_loop_counts = np.zeros(cache.num_islands, dtype=np.float32)
            np.add.at(island_loop_counts, cache.loop_island_ids, 1.0)
            island_loop_counts[island_loop_counts < 1.0] = 1.0
            cache.island_centers = island_uv_sums / island_loop_counts[:, np.newaxis]
