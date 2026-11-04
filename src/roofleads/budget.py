from decimal import Decimal, ROUND_HALF_UP


def decimal_to_micro(value: Decimal) -> int:
    return int((value * 1_000_000).to_integral_value(rounding=ROUND_HALF_UP))


def micro_to_money(micro: int) -> str:
    sign = "-" if micro < 0 else ""
    micro = abs(micro)
    whole = micro // 1_000_000
    frac = micro % 1_000_000
    return f"{sign}{whole}.{frac:06d}"


class Budget:
    """Lifetime spend recorded in one cache folder, plus the spend of this process."""

    def __init__(
        self,
        *,
        max_credits: int,
        max_apify_micro: int,
        lifetime_hunter: int = 0,
        lifetime_apify_micro: int = 0,
    ) -> None:
        self.max_credits = max_credits
        self.max_apify_micro = max_apify_micro
        self.lifetime_hunter = lifetime_hunter
        self.lifetime_apify_micro = lifetime_apify_micro
        self.run_hunter = 0
        self.run_apify_micro = 0
        self.stopped_reason: str | None = None

    def can_afford_credits(self, credits: int) -> bool:
        if credits <= 0:
            return True
        return self.lifetime_hunter + credits <= self.max_credits

    def can_afford_apify(self, micro: int) -> bool:
        if micro <= 0:
            return True
        return self.lifetime_apify_micro + micro <= self.max_apify_micro

    def charge_credits(self, credits: int) -> None:
        self.lifetime_hunter += credits
        self.run_hunter += credits

    def charge_apify(self, micro: int) -> None:
        self.lifetime_apify_micro += micro
        self.run_apify_micro += micro

    def stop_for_credits(self, credits: int, what: str) -> None:
        if self.stopped_reason:
            return
        projected = self.lifetime_hunter + credits
        self.stopped_reason = (
            f"Stopped before {what}: it would use {credits} Hunter credit(s) and bring the "
            f"cache total to {projected}, above the --max-credits limit of {self.max_credits} "
            f"({self.lifetime_hunter} already recorded in this cache). "
            "Cached lookups are free. Raise --max-credits to pay for more, "
            "or pass a new --cache-dir to start a separate budget."
        )

    def stop_for_apify(self, micro: int, what: str) -> None:
        if self.stopped_reason:
            return
        projected = micro_to_money(self.lifetime_apify_micro + micro)
        already = micro_to_money(self.lifetime_apify_micro)
        cap = micro_to_money(self.max_apify_micro)
        estimate = micro_to_money(micro)
        self.stopped_reason = (
            f"Stopped before {what}: the estimate of ${estimate} would bring Apify spend "
            f"in this cache to ${projected}, above the --max-apify-usd limit of ${cap} "
            f"(${already} already recorded). "
            "Cached city searches are free. Raise --max-apify-usd to continue, "
            "or pass a new --cache-dir to start a separate budget."
        )
