"""휴머노이드 로봇 아이콘 — 트레이(pystray)와 exe(.ico)가 같은 그림을 공유.

이미지 에셋 없이 PIL로 그린다. 색은 웹 로고와 같은 Lodestar 블루 계열
(다크 accent #6c9bee — 윈도우 기본 다크 트레이에서 잘 보임) + 안테나
불빛은 기존 트레이 별의 노랑을 승계.

빌드 시 `python robot_icon.py icon.ico`로 exe 아이콘(.ico)을 생성한다
(build.bat이 호출 — 저장소엔 바이너리를 커밋하지 않는다).
"""

from PIL import Image, ImageDraw

BODY = "#6c9bee"   # 로열블루(다크 테마 --accent)
FACE = "#06141d"   # accent 위 글자색(--on-accent 다크)과 동일
LIGHT = "#facc15"  # 안테나 불빛 — 기존 별 색


def draw_humanoid(size: int = 64) -> Image.Image:
    """size×size RGBA 휴머노이드. 64 기준 좌표를 비율로 스케일해 어느
    사이즈로도 또렷하게 다시 그린다(리사이즈로 뭉개지 않음)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64.0

    def box(x0: float, y0: float, x1: float, y1: float) -> list[float]:
        return [x0 * s, y0 * s, x1 * s, y1 * s]

    # 안테나(대 + 불빛)
    d.rectangle(box(30.5, 6, 33.5, 13), fill=BODY)
    d.ellipse(box(28, 1, 36, 9), fill=LIGHT)
    # 머리 + 눈
    d.rounded_rectangle(box(16, 13, 48, 33), radius=6 * s, fill=BODY)
    d.ellipse(box(23, 19, 29, 25), fill=FACE)
    d.ellipse(box(35, 19, 41, 25), fill=FACE)
    # 몸통
    d.rounded_rectangle(box(19, 37, 45, 55), radius=6 * s, fill=BODY)
    # 팔
    d.rounded_rectangle(box(8, 38, 15, 52), radius=3.5 * s, fill=BODY)
    d.rounded_rectangle(box(49, 38, 56, 52), radius=3.5 * s, fill=BODY)
    # 다리
    d.rounded_rectangle(box(22, 57, 29, 63), radius=3 * s, fill=BODY)
    d.rounded_rectangle(box(35, 57, 42, 63), radius=3 * s, fill=BODY)
    return img


def save_ico(path: str) -> None:
    """exe 아이콘용 멀티 사이즈 .ico — 각 사이즈를 따로 그려 작은 크기도 또렷하게."""
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [draw_humanoid(n) for n in sizes]
    imgs[-1].save(path, format="ICO", append_images=imgs[:-1],
                  sizes=[(n, n) for n in sizes])


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "icon.ico"
    save_ico(out)
    print(f"{out} 생성 완료")
