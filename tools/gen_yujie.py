# 环境变量：IMG_BASE（接口地址）、IMG_KEY（密钥，只放环境变量，别写进文件）、IMG_MODEL（可选）、SHEET_REF（参考图）
"""用图像 API 生成成熟御姐的立绘（key 只从环境变量读，不写任何文件）。
流程：
  1) sit：以设定图正面全身图为参考（/v1/images/edits），背景要求纯绿幕
  2) 其余姿势：以 sit 的原图为参考，只改表情/姿势
  3) 每张抠绿幕 -> 透明 PNG，并统一脚底位置/水平中心，保存到 OUT
用法： python gen.py sit   |   python gen.py happy wave ...   |   python gen.py all
"""
import os, sys, json, base64, urllib.request, urllib.error, uuid, time, threading
import numpy as np
from PIL import Image

BASE = os.environ["IMG_BASE"].rstrip("/")
KEY = os.environ["IMG_KEY"]
MODEL = os.environ.get("IMG_MODEL", "gpt-image-2.5-flare")
OUT = os.environ.get("IMG_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skins", "yujie"))
SHEET = os.environ.get("SHEET_REF", "ref_front.png")   # 设定图正面全身图（白底，2:3）
RAW = os.path.join(OUT, "raw")
os.makedirs(RAW, exist_ok=True)

BG = "solid flat pure chroma-key green (#00FF00) background with no gradient, no floor, no shadow, no green in the character"
COMMON = (
    "A mature, tall, elegant young woman with an onee-san (older sister) aura, slender figure about 8 heads tall, calm and slightly languid expression. "
    "Keep the character design exactly as in the reference: very long orange hair, amber eyes, orange chrysanthemum hair ornament with black ribbon bow and gold tassels on her left side (the viewer's right), "
    "white ruffled high-collar blouse with orange flower brooch and black ribbon tie, cream capelet with orange chrysanthemum embroidery, black corset belt with gold chain and tassel, "
    "long three-panel skirt in cream, black and orange with a lace hem, cream lace-up ankle boots. She holds a brown leather book with gold corners and an orange flower emblem. "
    "Japanese anime illustration, clean cel shading, thin sharp dark brown outlines, high quality, crisp edges. "
    "Full body from the top of the head to the soles of the boots, standing, character centered in a tall vertical canvas (2:3), feet touching the bottom edge, "
    f"{BG}. No text, no speech bubbles, no other characters."
)
POSES = {
    "sit": "Relaxed standing pose facing the viewer, looking ahead, a faint knowing smile, one hand holding the book at her side, the other arm resting naturally. Redraw the reference character as a polished full-body illustration, keeping her outfit and hairstyle faithful.",
    "blink": "Identical to the reference image, but both eyes are gently closed with lowered lashes.",
    "happy": "Eyes in happy crescents, a soft warm smile, head tilted slightly, hugging the book in front of her.",
    "cheer": "Cheerful with sparkling eyes, one fist raised to shoulder height (staying below the top of her head), the other hand holding the book.",
    "wave": "Smiling greeting, one hand raised beside her face waving with the palm facing outward, the other hand holding the book, the hand stays below the top of her head.",
    "pout": "Puffed cheek, slightly furrowed brows, glancing sideways, arms crossed with the book tucked in, a tsundere expression.",
    "worried": "Slightly furrowed brows, a small frown, hugging the book to her chest, shoulders slightly drawn in.",
    "working": "Looking down at an open book held in one hand, the other hand holding a page, eyes lowered, a focused expression.",
    "sleep": "Dozing while standing, head tilted to one side, eyes closed, relaxed mouth, the book loosely tucked under her arm.",
    "shy": "Shy and a little flustered, a light blush on her cheeks, eyes glancing away to the side, one hand lifting the book to partly cover her chin, a bashful small smile.",
    "tease": "Playfully teasing smirk, one eyebrow raised, eyes half-lidded and amused, one finger raised to her lips as if keeping a secret, the other hand holding the book at her side, a mischievous but warm expression.",
    "laugh": "Laughing happily, eyes closed in crescents, mouth open in a bright laugh, one hand covering her mouth lightly, the other arm holding the book against her side.",
    "think": "Thoughtful pose, one hand under her chin with the index finger resting on her cheek, eyes looking up and to the side, the other arm holding the book, a curious expression.",
    "yawn": "Sleepy, yawning with one hand covering her open mouth, eyes squeezed shut, the other hand holding the book loosely, a relaxed drowsy posture.",
    "drag": "Startled, wide eyes, a small o-shaped mouth, hugging the book tightly with both hands, hair and skirt floating slightly upward as if lifted by the collar.",
}


def _send(req, timeout):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {"error": "http %s" % e.code}
    except Exception as e:
        return -1, {"error": repr(e)}


def post_multipart(path, fields, files, timeout=420):
    b = "----pet" + uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, (fn, data, ct) in files.items():
        body += (f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\nContent-Type: {ct}\r\n\r\n').encode() + data + b"\r\n"
    body += f"--{b}--\r\n".encode()
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    req.add_header("Authorization", "Bearer " + KEY)
    req.add_header("Content-Type", "multipart/form-data; boundary=" + b)
    req.add_header("User-Agent", "claude-desk-pet-tool")
    return _send(req, timeout)


def key_green(im):
    """抠绿幕：绿色明显高于红蓝 -> 透明；边缘去绿溢出"""
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    spill = g - np.maximum(r, b)                      # 越大越“绿”
    alpha = np.clip(1.0 - (spill - 18.0) / 60.0, 0.0, 1.0)
    alpha = np.where(spill < 18.0, 1.0, alpha)
    g2 = np.where(spill > 0, np.minimum(g, np.maximum(r, b) + 4.0), g)   # 去绿溢出
    # 按色相再清一遍：这个角色没有黄绿/绿色的东西（头发橙、金边偏黄 <55°），色相落在 62°~175° 且够饱和的都是绿幕残留
    hsv = np.asarray(Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGB").convert("HSV")).astype(np.float32)
    hue = hsv[..., 0] * 360.0 / 255.0
    sat = hsv[..., 1] / 255.0
    greenish = (hue >= 62) & (hue <= 175) & (sat > 0.22)
    soft = np.clip((hue - 56.0) / 10.0, 0.0, 1.0)                        # 56°~66° 之间平滑过渡
    alpha = np.where(greenish, np.minimum(alpha, 1.0 - soft), alpha)
    # 深色描边和绿幕混出来的“橄榄色”（g 接近 r、b 明显更低）：橙发(g/r<0.7)、金边(g/r≈0.8)都不会落在这里
    olive = (g >= 0.88 * r) & (b < 0.85 * g) & (sat > 0.30) & (hue >= 46)
    alpha = np.where(olive, np.minimum(alpha, 0.0), alpha)
    out = np.dstack([r, g2, b, alpha * 255.0]).clip(0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def align(im, target_bottom=1528, target_cx=512):
    """统一脚底位置和水平中心（按下方 6% 的内容算脚的中心），画布 1024x1536"""
    im = im.resize((1024, 1536), Image.LANCZOS) if im.size != (1024, 1536) else im
    al = np.asarray(im.getchannel("A"))
    rows = np.where(al.max(axis=1) > 20)[0]
    if len(rows) == 0:
        return im
    top, bottom = rows[0], rows[-1]
    foot_rows = al[max(top, bottom - int((bottom - top) * 0.06)):bottom + 1]
    cols = np.where(foot_rows.max(axis=0) > 20)[0]
    cx = (cols[0] + cols[-1]) / 2.0
    canvas = Image.new("RGBA", im.size, (0, 0, 0, 0))
    canvas.alpha_composite(im, (int(round(target_cx - cx)), int(target_bottom - bottom)))
    return canvas


def gen(name, ref_path):
    prompt = COMMON + " " + POSES[name]
    if name != "sit":
        prompt += " Keep exactly the same character, outfit, hair, hair ornament placement, proportions, scale and composition as the reference image; only change the expression/pose as described."
    data = open(ref_path, "rb").read()
    t0 = time.time()
    st, js = -1, {}
    for extra in ({"size": "1024x1536", "quality": "high"}, {"size": "1024x1536"}):
        fields = dict(model=MODEL, prompt=prompt, n="1", **extra)
        st, js = post_multipart("/v1/images/edits", fields, {"image": ("ref.png", data, "image/png")})
        if st == 200:
            break
        print(" ", name, "retry:", st, str(js)[:160], flush=True)
    if st != 200:
        print(name, "FAILED", st, str(js)[:300], flush=True)
        return None
    d = (js.get("data") or [{}])[0]
    raw = base64.b64decode(d["b64_json"]) if d.get("b64_json") else urllib.request.urlopen(d["url"], timeout=120).read()
    rawp = os.path.join(RAW, name + ".png")
    open(rawp, "wb").write(raw)
    final = align(key_green(Image.open(rawp)))
    final.save(os.path.join(OUT, name + ".png"))
    print(name, "ok", round(time.time() - t0, 1), "s", flush=True)
    return rawp


if __name__ == "__main__":
    names = sys.argv[1:]
    if names == ["rekey"]:                                # 用已保存的原图重新抠绿幕，不调用接口
        for n in POSES:
            align(key_green(Image.open(os.path.join(RAW, n + ".png")))).save(os.path.join(OUT, n + ".png"))
        sys.exit(0)
    if names == ["all"]:
        names = [n for n in POSES if n != "sit"]
    if "sit" in names:
        gen("sit", SHEET)
        names = [n for n in names if n != "sit"]
    ref = os.path.join(RAW, "sit.png")
    threads = []
    for n in names:                                    # 其余姿势并行出，最多 3 个同时
        while sum(t.is_alive() for t in threads) >= 3:
            time.sleep(1)
        t = threading.Thread(target=gen, args=(n, ref))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
