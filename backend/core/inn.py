import re


def is_valid_inn(inn: str) -> bool:
    if not re.fullmatch(r"\d{10}|\d{12}", inn):
        return False

    digits = [int(d) for d in inn]

    def checksum(coefficients: tuple[int, ...]) -> int:
        return sum(c * d for c, d in zip(coefficients, digits)) % 11 % 10

    if len(inn) == 10:
        return checksum((2, 4, 10, 3, 5, 9, 4, 6, 8)) == digits[9]

    return (
        checksum((7, 2, 4, 10, 3, 5, 9, 4, 6, 8)) == digits[10]
        and checksum((3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)) == digits[11]
    )
