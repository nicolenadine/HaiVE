import math


class TokenCounter:
    @staticmethod
    def estimate(text: str) -> int:
        return math.ceil(len(text) / 4)
