# -*- coding: utf-8 -*-
"""运镜解算（camera movement resolver）· cinematic-whitebox

问题：分镜的运镜以前只能隐含在 loc_a→loc_b 的坐标差里。
      为了做出一点「推进」，作者必须手填两个靠得很近的三维点，
      既看不出意图，也无法区分「推进」与「横移」与「真的固定机位」。
      结果：0.14m 的漂移被当成推进，或者该推的镜头根本没人写。

做法：把运镜提升为显式字段 move，用摄影术语声明，由本模块解算成端点位移。

    move = {'type': 'dolly', 'distance': 0.35, 'ease': 'inout', 'framing': 'auto'}

      type      dolly    沿光轴推进（>0）/ 拉远（<0）        ← 最常用
                truck    横移（>0 向画面右）
                pedestal 升降（>0 升）
                arc      围绕注视点环绕，单位 deg
                zoom     只改焦距（不改位姿），distance 为 lens 增量
                static   固定机位（显式声明，便于校验）
      distance  米（zoom 为 mm）
      ease       inout（默认，两端缓）/ linear / in / out
      sync_aim   False（默认）：机位推进、注视点留住 → 主体在画中变大（真实推进）
                True：注视点跟着机位走 → 焦点保持、只有视差变化（跟拍）
      framing    'auto'（默认，推荐）：按初始视线余弦比例补偿注视点，
                让主体留在原本的画框位置
                0.0：不补偿。主体保持初始视差与相对位置，但机位前移后
                     可能被挤出画框，或让近处前景占满画面
                1.0：注视点与机位同步平移 → 构图完全锁定，主体留在原位

关键语义：
  * 推进 = 沿「机位→注视点」光轴方向前进，因此与主体的距离真的变小，
    画面呈现整体向外扩散。它不是把 loc_b 写近一点那么简单——那样
    注视点也在动，主体可能不变大。
  * **framing 不改变放大倍率**。机位终点由 move 决定，主体到机位的距离
    因而固定：放大倍率 = 起始距离 ÷ 终点距离，与 framing 无关。
    framing 只决定主体落在画框内的「位置」。所以 0.0 与 1.0 的放大完全相同，
    差别是构图还能不能用——这也是长焦近景必须给补偿的原因。
  * dolly 与 zoom 正交，可叠加：dolly 给透视与遮挡变化，zoom 给紧凑度。
    需要滑动变焦（眩晕/认知突变）时，让两者反向即可。
  * ease 决定速度曲线；推进一般用 inout（缓起缓停），
    情绪压迫可用 in，突袭可用 out。

校验：解算后必须核对「到位移」「主体是否单调靠近」「主体是否还在画框内」。
     放大倍率要用**主体点**度量，不能用注视点——注视点已被 framing 补偿前移，
     用它算会把推进误报成几乎没动（0.35m 推进：用注视点 1.04×，用主体 1.20×）。
      dp_build.py 会把解算结果写进分镜元数据的 motion 字段，供 QA 复查：

        'motion': {'type':'dolly', 'path_m':0.35, 'ease':'inout', 'framing':0.8,
                   'declared':{...}, 'resolved':{'loc_a':[...], 'loc_b':[...]},
                   'resolved_aim':{'aim_a':[...], 'aim_b':[...]}}

      路径长 0.75m 而画面放大 1.56×，是「推进」而不是「漂移」的判据。
"""
import math

try:
    from mathutils import Vector
except ImportError:                                     # 允许脱离 Blender 做单元测试
    class Vector(tuple):
        """极简替身：与 mathutils.Vector 一致，length 是属性而非方法。"""
        def __new__(cls, v):
            return super().__new__(cls, (float(v[0]), float(v[1]), float(v[2])))

        def __add__(self, o):
            return Vector((self[0]+o[0], self[1]+o[1], self[2]+o[2]))

        def __sub__(self, o):
            return Vector((self[0]-o[0], self[1]-o[1], self[2]-o[2]))

        def __mul__(self, k):
            return Vector((self[0]*k, self[1]*k, self[2]*k))

        __rmul__ = __mul__

        @property
        def length(self):
            return math.sqrt(self[0]**2 + self[1]**2 + self[2]**2)

        def normalized(self):
            n = self.length or 1.0
            return Vector((self[0]/n, self[1]/n, self[2]/n))

        def dot(self, o):
            return self[0]*o[0] + self[1]*o[1] + self[2]*o[2]

        def cross(self, o):
            return Vector((self[1]*o[2]-self[2]*o[1],
                           self[2]*o[0]-self[0]*o[2],
                           self[0]*o[1]-self[1]*o[0]))

MOVE_TYPES = ('dolly', 'truck', 'pedestal', 'arc', 'zoom', 'static')

MOVE_LABEL = {
    'dolly': '推进/拉远（沿光轴）',
    'truck': '横移（左右）',
    'pedestal': '升降',
    'arc': '环绕',
    'zoom': '焦距推（不改位姿）',
    'static': '固定机位',
}

# 阈值：低于此位移视为「没有运镜」，用于校验告警
STATIC_EPS = 0.06

# framing='auto' 的补偿系数上限。
#
# 几何事实：让主体「原样居中」与让主体「变大」互相冲突——
#   注视点完全不动（0.0）→ 主体放大最多，但会偏离画框
#   注视点与机位同速（1.0）→ 构图完全锁定，但主体大小不变（推进感消失）
# 且主体距机位 d 时，推进位移 m 会带来 m/d 的角位移；长焦近景（d 小）尤其明显。
# 因此 auto 取一个折中：既让主体留在画框内，又保留可读的放大。
AUTO_FRAMING_CEIL = 0.8


def auto_framing(p, a, p_d):
    """按初始视线余弦比例求取景补偿系数。

    cosθ = (机位→注视点) 与 (运动方向) 的夹角余弦。
    主体本来就在画面中心时 cosθ≈1，补偿最多；横移或环绕时 cosθ≈0，几乎不补偿
    （此时保留视差正是想要的效果）。
    """
    view = Vector(a) - Vector(p)
    if view.length < 1e-6 or p_d.length < 1e-6:
        return 0.0
    cos_t = view.normalized().dot(p_d.normalized())
    return max(0.0, min(1.0, cos_t)) * AUTO_FRAMING_CEIL


def ease_apply(kind, t):
    """把线性进度 t∈[0,1] 映射成缓动进度。"""
    t = max(0.0, min(1.0, t))
    if kind == 'linear':
        return t
    if kind == 'in':
        return t * t
    if kind == 'out':
        return 1.0 - (1.0 - t) ** 2
    # inout（默认）：两端缓的余弦缓动，等价 smoothstep 的手感
    return 0.5 - 0.5 * math.cos(math.pi * t)


def smoothstep(t):
    """旧版 loc_a→loc_b 使用的插值曲线，保留以保证向后兼容。"""
    return t * t * (3 - 2 * t)


def move_vectors(move, p, aim):
    """把 move 解算成世界空间位移向量（不含缓动）。

    相机朝向按「光轴」定义：fwd = normalize(aim - p)。
    横移轴 = fwd × up，升降轴固定世界 Z。
    """
    fwd = Vector(aim) - Vector(p)
    if fwd.length < 1e-6:
        fwd = Vector((0.0, 0.0, -1.0))
    fwd = fwd.normalized()
    up = Vector((0.0, 0.0, 1.0))
    right = fwd.cross(up)
    if right.length < 1e-6:
        right = Vector((1.0, 0.0, 0.0))
    right = right.normalized()

    t = (move or {}).get('type', 'static')
    d = float((move or {}).get('distance', 0.0) or 0.0)

    if t == 'dolly':
        return fwd * d, fwd
    if t == 'truck':
        return right * d, fwd
    if t == 'pedestal':
        return Vector((0.0, 0.0, d)), fwd
    if t == 'arc':
        ang = math.radians(float((move or {}).get('angle', 0.0) or 0.0))
        radius = fwd.length
        return right * (math.sin(ang) * radius) + fwd * ((math.cos(ang) - 1.0) * radius), fwd
    return Vector((0.0, 0.0, 0.0)), fwd


def resolve_move(sub):
    """由 move 字段解算 (起点, 终点, 焦距缩放, 说明)。缺省时退回 loc 端点。

    sub 需要 'loc'（(a, b) 两点）与 'aim'；'lens' 用于 zoom 换算。
    """
    loc = sub['loc']
    p0, p1 = Vector(loc[0]), Vector(loc[1])
    aim = sub.get('aim') or ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    a0 = Vector(aim[0])
    move = sub.get('move')

    if not move:
        return p0, p1, 1.0, None                      # 旧格式，交给调用方标注 legacy

    t = move.get('type', 'static')
    if t not in MOVE_TYPES:
        raise ValueError(f"未知运镜类型 {t!r}；可选 {MOVE_TYPES}")

    if t == 'static':
        return p0, p0, 1.0, {'type': t, 'label': MOVE_LABEL[t], 'path_m': 0.0}

    if t == 'zoom':
        lens = max(1e-6, float(sub.get('lens', 1.0)))
        zoom = 1.0 + float(move.get('distance', 0.0) or 0.0) / lens
        return p0, p0, zoom, {'type': t, 'label': MOVE_LABEL[t],
                              'path_m': 0.0, 'lens_zoom': round(zoom, 4),
                              'framing': 0.0, 'framing_mode': 'fixed'}

    p_d, fwd = move_vectors(move, p0, a0)
    info = {
        'type': t,
        'label': MOVE_LABEL[t],
        'path_m': round(p_d.length, 3),
        'dir': [round(v, 3) for v in p_d.normalized()] if p_d.length > 1e-6 else [0.0, 0.0, 0.0],
        'ease': move.get('ease', 'inout'),
        'sync_aim': bool(move.get('sync_aim', False)),
    }
    raw_fr = move.get('framing', 'auto')
    if isinstance(raw_fr, str):
        # 'auto'：按初始视线余弦比例补偿（见 auto_framing）
        info['framing'] = round(auto_framing(p0, a0, p_d), 4)
        info['framing_mode'] = 'auto'
    else:
        info['framing'] = max(0.0, min(1.0, float(raw_fr or 0.0)))
        info['framing_mode'] = 'fixed'
    if info['sync_aim']:
        return p0, p0 + p_d, 1.0, info
    # 默认：机位动、注视点留住 → 主体在画面中真的变大
    return p0, p0 + p_d, 1.0, info


def aim_endpoints(sub, p_a, p_b, info):
    """按 framing 把注视点端点也解算出来。

    framing=0：注视点不动（视差最强，主体会在画框内位移）
    framing=1：注视点与机位同速同向（主体大小不变，等价跟拍）
    auto 已由 resolve_move 折算成具体系数，此处只做线性施加。
    """
    aim = sub.get('aim') or ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    a_a, a_b = Vector(aim[0]), Vector(aim[1])
    if not info:
        return a_a, a_b
    frac = float(info.get('framing', 0.0) or 0.0)
    frac = max(0.0, min(1.0, frac))
    if frac <= 0.0:
        return a_a, a_b
    d = p_b - p_a
    a_b = a_b + d * frac
    return a_a, a_b


def camera_at(sub, out_frame):
    """给定输出帧，返回该帧的 (机位, 注视点, 焦距)。用于独立复算与单元测试。"""
    p_a, p_b, zoom, info = resolve_move(sub)
    a_a, a_b = aim_endpoints(sub, p_a, p_b, info)
    span = max(1, sub['end'] - sub['start'])
    t = ease_apply((info or {}).get('ease', 'inout') if info else 'inout',
                   (out_frame - sub['start']) / span)

    def mix(u, v):
        if isinstance(u, Vector):
            return Vector((u[0] + (v[0] - u[0]) * t,
                           u[1] + (v[1] - u[1]) * t,
                           u[2] + (v[2] - u[2]) * t))
        return Vector((u[0] + (v[0] - u[0]) * t,
                       u[1] + (v[1] - u[1]) * t,
                       u[2] + (v[2] - u[2]) * t))

    p = mix(p_a, p_b)
    a = mix(a_a, a_b)
    lens = float(sub.get('lens', 50.0)) * (1.0 + (zoom - 1.0) * t)
    return p, a, lens


def verify_motion(sub, frames=None, static_eps=STATIC_EPS, subject=None):
    """自检：位移 / 主体放大倍率 / 构图保持程度。

    关键：放大倍率必须对「主体」度量，不能对注视点度量。
    注视点会被 framing 补偿前移，用它算距离会把推进误报成几乎没动
    （例：0.35m 推进 + auto 补偿，用注视点算只有 1.04×，用主体算才是 1.20×）。

    subject=None 时退回使用初始注视点（此时两者相同，仅在 framing=0 时准确）。
    """
    frames = frames or [sub['start'], (sub['start'] + sub['end']) // 2, sub['end']]
    p_a, p_b, zoom, info = resolve_move(sub)
    a_a, a_b = aim_endpoints(sub, p_a, p_b, info)
    path = (p_b - p_a).length
    aim_shift = (a_b - a_a).length

    ref = Vector(subject) if subject is not None else a_a
    dists = []
    for f in frames:
        p, _a, _lens = camera_at(sub, f)
        dists.append((ref - p).length)
    mono = all(dists[i] >= dists[i + 1] - 1e-6 for i in range(len(dists) - 1))
    framing = float((info or {}).get('framing', 0.0) or 0.0)
    scale = round(dists[0] / dists[-1], 3) if dists[-1] > 1e-6 else None

    return {
        'type': (info or {}).get('type', 'legacy'),
        'path_m': round(path, 4),
        'aim_shift_m': round(aim_shift, 4),
        'framing': framing,
        'subject_used': [round(float(v), 3) for v in ref],
        'dists': [round(d, 4) for d in dists],
        'scale': scale,
        'frame_lock': framing >= 0.99,
        'approach_monotonic': mono,
        'effective': (path >= static_eps) or abs(zoom - 1.0) > 1e-6,
    }


if __name__ == '__main__':
    # 自测：工程实际采用的配置（L6 DP02，90mm，主体距机位 2.09m）
    # 应当给出 0.35m 位移与约 1.2 倍放大；'auto' 折算出的取景补偿为 0.8
    sub = {
        'lens': 90, 'start': 49, 'end': 104,
        'loc': ((0.95, -1.70, 1.48), (0.95, -1.70, 1.48)),
        'aim': ((-0.12, 0.05, 1.06), (-0.12, 0.05, 1.06)),
        'move': {'type': 'dolly', 'distance': 0.35, 'ease': 'inout', 'framing': 'auto'},
    }
    print('L6 DP02（工程实际配置）=', verify_motion(sub, subject=sub['aim'][0]))
    print()
    # 对照：完全不补偿 vs 完全锁定（说明为何 'auto' 是折中）
    for fr in (0.0, 'auto', 1.0):
        s = dict(sub, move={'type': 'dolly', 'distance': 0.35, 'ease': 'inout', 'framing': fr})
        v = verify_motion(s, subject=sub['aim'][0])
        print(f"  framing={str(fr):5s} 补偿={v['framing']:.2f} 主体放大={v['scale']}× "
              f"到主体距离={v['dists'][0]}→{v['dists'][-1]} m")
    print()
    for t in ('static', 'truck', 'pedestal', 'zoom', 'arc'):
        s2 = dict(sub, move={'type': t, 'distance': 0.5, 'angle': 10})
        v = verify_motion(s2)
        print(f"  {t:9s} path={v['path_m']:5.3f}m 放大={v['scale']}× "
              f"单调={v['approach_monotonic']} 有效={v['effective']}")
