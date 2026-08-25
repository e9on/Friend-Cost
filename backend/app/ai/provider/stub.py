"""실제 모델을 붙이기 전까지 파이프라인을 돌리는 스텁 Provider.

기준 명세 13장: 특정 LLM Provider·Model은 성능 평가 이후에 정한다.
그때까지 파이프라인 전체를 실행하고 검증할 수 있어야 하므로, 스키마에 맞는
응답을 만들어 주는 가짜를 둔다.

성질:
- **결정론적이다.** 같은 입력에는 항상 같은 출력. 테스트가 흔들리지 않는다.
- **입력에 따라 달라진다.** 대화가 달라지면 결과도 달라져서 파이프라인이
  실제로 데이터를 흘리고 있는지 눈으로 확인할 수 있다.
- 품질은 없다. 이것으로 결과의 타당성을 평가하면 안 된다.
"""

import hashlib
import json

from app.ai.provider.base import LlmRequest, LlmResponse

_HEADLINES = (
    "서로 챙기지만 균형이 조금 기운 사이",
    "말수는 적어도 오래가는 사이",
    "요즘 들어 뜸해진 사이",
    "티격태격해도 붙어 있는 사이",
)
_SECTION_TITLES = ("연락의 흐름", "대화의 온도", "지켜볼 지점")
_SECTION_BODIES = (
    "먼저 말을 거는 쪽이 대체로 정해져 있다. 한쪽이 멈추면 대화도 함께 멈추는 흐름이 보인다.",
    "가벼운 잡담이 대부분이지만 가끔 속내를 꺼내는 순간이 있다. 그 순간에 상대의 반응이 나쁘지 않다.",
    "약속이 미뤄지는 일이 몇 번 반복됐다. 큰 문제는 아니지만 쌓이면 서운함이 된다.",
)
_ADVICE = (
    "다음 약속은 날짜부터 먼저 정해 보자.",
    "가끔은 먼저 안부를 물어보는 것도 좋겠다.",
    "고맙다는 말을 한 번쯤 직접 해보자.",
)


class StubLlmProvider:
    """호출 없이 스키마에 맞는 응답을 지어낸다."""

    name = "stub"

    async def complete(self, request: LlmRequest) -> LlmResponse:
        seed = int.from_bytes(
            hashlib.sha256(request.user.encode("utf-8")).digest()[:8], "big"
        )
        if request.purpose == "report":
            text = self._report(seed)
        else:
            text = self._analysis(seed)
        return LlmResponse(
            text=text,
            input_tokens=len(request.system) // 3 + len(request.user) // 3,
            output_tokens=len(text) // 3,
        )

    @staticmethod
    def _pick(seed: int, shift: int, low: int, high: int) -> int:
        return low + ((seed >> shift) % (high - low + 1))

    def _analysis(self, seed: int) -> str:
        payload = {
            "emotionalTone": {
                "me": self._pick(seed, 0, 40, 95),
                "peer": self._pick(seed, 5, 40, 95),
            },
            "affectionSignals": {
                "me": self._pick(seed, 10, 20, 90),
                "peer": self._pick(seed, 15, 20, 90),
            },
            "effortLevel": {
                "me": self._pick(seed, 20, 30, 95),
                "peer": self._pick(seed, 25, 30, 95),
            },
            "conflictLevel": self._pick(seed, 30, 0, 60),
            "topicDepth": self._pick(seed, 35, 20, 90),
            "promiseSignals": {
                "proposed": self._pick(seed, 40, 0, 8),
                "fulfilled": self._pick(seed, 43, 0, 5),
                "declined": self._pick(seed, 46, 0, 3),
            },
            "moneySignals": {
                "lent": self._pick(seed, 49, 0, 2),
                "borrowed": self._pick(seed, 51, 0, 2),
                "resolved": self._pick(seed, 53, 0, 2),
            },
            "notableMoments": ["생일을 먼저 챙긴 일이 있었다", "약속이 두 번 미뤄졌다"],
        }
        return json.dumps(payload, ensure_ascii=False)

    def _report(self, seed: int) -> str:
        first = self._pick(seed, 0, 0, len(_SECTION_TITLES) - 1)
        second = (first + 1) % len(_SECTION_TITLES)
        payload = {
            "headline": _HEADLINES[self._pick(seed, 8, 0, len(_HEADLINES) - 1)],
            "summary": (
                "연락은 꾸준히 이어지고 있지만 시작하는 쪽이 한쪽으로 쏠려 있다. "
                "감정의 온도는 나쁘지 않아서 계기만 있으면 다시 균형을 찾을 수 있다."
            ),
            "sections": [
                {"title": _SECTION_TITLES[first], "body": _SECTION_BODIES[first]},
                {"title": _SECTION_TITLES[second], "body": _SECTION_BODIES[second]},
            ],
            "advice": _ADVICE[self._pick(seed, 16, 0, len(_ADVICE) - 1)],
        }
        return json.dumps(payload, ensure_ascii=False)
