"""카카오톡 화면을 닮은 캡처 이미지를 그린다.

실제 캡처가 없어도 OCR을 평가할 수 있게 하려는 것이다.

**핵심은 정답을 안다는 점이다.** 우리가 직접 그렸으므로 어느 메시지가 누구
것인지 알고 있다. 그래서 화자 판별 정확도를 사람 눈이 아니라 숫자로 잴 수 있다.
`AI-모델-선정-보고서.md` 8.2가 "자동으로 잴 수 없다"고 한 지표를 여기서는
잴 수 있다.

한계도 분명하다. 실제 캡처에는 안티에일리어싱, 압축 노이즈, 프로필 사진,
읽음 표시, 다양한 폰트 두께가 섞인다. 여기서 잘 나온다고 실제에서도
잘 나온다는 보장은 없다. **하한선을 재는 것**이지 상한선이 아니다.
"""

import json
import random
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _console import force_utf8  # noqa: E402

force_utf8()

WIDTH = 1080
FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
FONT_BOLD = "C:/Windows/Fonts/malgunbd.ttf"

# 카카오톡 밝은 테마 색
BG = (185, 200, 217)
MY_BUBBLE = (254, 229, 0)
PEER_BUBBLE = (255, 255, 255)
TEXT = (30, 30, 30)
STAMP = (120, 128, 140)
DATE_PILL = (0, 0, 0, 40)

EDGE = 28
PROFILE = 92
BUBBLE_PAD_X = 22
BUBBLE_PAD_Y = 14
GAP = 18
MAX_BUBBLE_W = 660

ME_LINES = (
    "내일 시간 돼?",
    "ㅋㅋㅋㅋ 진짜 웃기다",
    "밥 먹었어?",
    "그럼 그때 보자",
    "고마워 진짜",
    "나도 그렇게 생각해",
    "오늘 좀 늦을 것 같아",
    "사진 보냈어 확인해봐",
    "다음 주에 시간 어때",
    "그거 진짜야?",
)
PEER_LINES = (
    "어 괜찮아",
    "미안 좀 늦을 듯",
    "다음에 보자",
    "웬일이야 먼저 연락을 다 하고",
    "알겠어 그때 연락할게",
    "ㅇㅇ",
    "나 지금 회사야",
    "그래 조심히 와",
    "완전 좋지",
    "헐 대박",
)


@dataclass
class Truth:
    """정답. 어느 위치의 어떤 텍스트가 누구 것인지."""

    speaker: str
    text: str
    stamp: str
    x: int
    y: int
    w: int
    h: int


def wrap(draw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if draw.textlength(candidate, font=font) > max_width and current:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


class KakaoRenderer:
    def __init__(self, seed: int = 0, font_size: int = 30, senders: tuple[str, ...] = ()) -> None:
        self.rng = random.Random(seed)
        self.font = ImageFont.truetype(FONT_PATH, font_size)
        self.stamp_font = ImageFont.truetype(FONT_PATH, 19)
        self.date_font = ImageFont.truetype(FONT_BOLD, 21)
        # 단체방이면 왼쪽 말풍선 위에 발신자 이름이 붙는다. 실제 카카오톡은
        # 본문보다 작은 글꼴을 쓴다. 이 비율이 감지의 근거이므로 지어내지 않고
        # 실제와 비슷하게 맞춘다
        self.name_font = ImageFont.truetype(FONT_PATH, int(font_size * 0.8))
        self.senders = senders
        self.truths: list[Truth] = []

    def render(self, turns: int, start_hour: int = 9, with_date: bool = True):
        height = 200 + turns * (140 if self.senders else 110)
        image = Image.new("RGB", (WIDTH, height), BG)
        draw = ImageDraw.Draw(image)
        y = 40

        if with_date:
            y = self._date_pill(draw, y, "2026년 8월 25일 화요일")

        hour, minute = start_hour, self.rng.randint(0, 20)
        for turn in range(turns):
            mine = self.rng.random() < 0.5
            pool = ME_LINES if mine else PEER_LINES
            text = pool[self.rng.randrange(len(pool))]
            stamp = f"오전 {hour}:{minute:02d}" if hour < 12 else f"오후 {hour - 12 or 12}:{minute:02d}"
            if not mine and self.senders:
                name = self.senders[self.rng.randrange(len(self.senders))]
                y = self._sender_name(draw, y, name)
            y = self._bubble(draw, y, text, stamp, mine)

            minute += self.rng.randint(1, 9)
            if minute >= 60:
                minute -= 60
                hour = (hour + 1) % 24

        return image.crop((0, 0, WIDTH, min(height, y + 40)))

    def _date_pill(self, draw, y: int, text: str) -> int:
        width = draw.textlength(text, font=self.date_font)
        x = (WIDTH - width) / 2
        draw.rounded_rectangle(
            [x - 18, y, x + width + 18, y + 38], radius=19, fill=(146, 165, 187)
        )
        draw.text((x, y + 8), text, font=self.date_font, fill=(255, 255, 255))
        return y + 38 + GAP + 6

    def _sender_name(self, draw, y: int, name: str) -> int:
        """말풍선 위 발신자 이름. 단체방에만 있다."""
        draw.text((EDGE + PROFILE, y), name, font=self.name_font, fill=(70, 78, 90))
        return y + self.name_font.size + 8

    def _bubble(self, draw, y: int, text: str, stamp: str, mine: bool) -> int:
        lines = wrap(draw, text, self.font, MAX_BUBBLE_W - BUBBLE_PAD_X * 2)
        line_height = self.font.size + 8
        text_w = max(draw.textlength(line, font=self.font) for line in lines)
        box_w = int(text_w) + BUBBLE_PAD_X * 2
        box_h = line_height * len(lines) + BUBBLE_PAD_Y * 2

        if mine:
            x = WIDTH - EDGE - box_w
            fill = MY_BUBBLE
        else:
            x = EDGE + PROFILE
            fill = PEER_BUBBLE
            # 프로필 자리
            draw.ellipse([EDGE, y, EDGE + 68, y + 68], fill=(206, 214, 224))

        draw.rounded_rectangle([x, y, x + box_w, y + box_h], radius=14, fill=fill)
        for index, line in enumerate(lines):
            draw.text(
                (x + BUBBLE_PAD_X, y + BUBBLE_PAD_Y + index * line_height),
                line,
                font=self.font,
                fill=TEXT,
            )

        stamp_w = draw.textlength(stamp, font=self.stamp_font)
        stamp_y = y + box_h - self.stamp_font.size - 4
        if mine:
            draw.text((x - stamp_w - 10, stamp_y), stamp, font=self.stamp_font, fill=STAMP)
        else:
            draw.text((x + box_w + 10, stamp_y), stamp, font=self.stamp_font, fill=STAMP)

        self.truths.append(
            Truth(
                speaker="me" if mine else "peer",
                text=text,
                stamp=stamp,
                x=x,
                y=y,
                w=box_w,
                h=box_h,
            )
        )
        return y + box_h + GAP


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="합성 카카오톡 캡처 생성")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", type=int, default=6, help="이미지 수")
    parser.add_argument("--turns", type=int, default=14, help="화면당 메시지 수")
    parser.add_argument(
        "--senders",
        nargs="*",
        default=[],
        help="단체방 발신자 이름. 주면 왼쪽 말풍선 위에 이름이 붙는다",
    )
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = []

    for index in range(args.count):
        renderer = KakaoRenderer(seed=index, senders=tuple(args.senders))
        image = renderer.render(args.turns, start_hour=9 + index, with_date=index == 0)
        name = f"{index:02d}.png"
        image.save(args.out / name)
        manifest.append({"image": name, "messages": [asdict(t) for t in renderer.truths]})
        print(f"  {name}  {image.width}x{image.height}  메시지 {len(renderer.truths)}개")

    truth_path = args.out / "truth.json"
    truth_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total = sum(len(item["messages"]) for item in manifest)
    print(f"\n캡처 {args.count}장, 메시지 {total}개")
    print(f"정답: {truth_path}")


if __name__ == "__main__":
    main()
