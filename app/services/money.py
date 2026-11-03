"""Conversão exata de centavos e arredondamento comercial explícito."""

from decimal import ROUND_HALF_UP, Decimal, localcontext

CENT = Decimal("0.01")


def from_cents(value: int) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        return (Decimal(value) / Decimal(100)).quantize(CENT)


def discounted(price: Decimal, percent: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        return (price * (Decimal(100) - percent) / Decimal(100)).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
