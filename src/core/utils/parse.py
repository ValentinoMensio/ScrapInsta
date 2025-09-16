import re

def parse_number(count_str: str) -> int:
    if not count_str:
        return 0

    count_str = count_str.lower().strip()

    multipliers = {
        'mil': 1_000,
        'k': 1_000,
        'm': 1_000_000,
        'millón': 1_000_000,
        'b': 1_000_000_000,
        'billón': 1_000_000_000,
    }

    multiplier = 1
    for suffix, mult in multipliers.items():
        if suffix in count_str:
            multiplier = mult
            count_str = count_str.replace(suffix, '').strip()
            break

    # Si es un número grande con separadores de miles tipo 4,127 o 1.234
    # lo limpiamos
    if re.match(r"^\d{1,3}([.,]\d{3})+$", count_str):
        count_str = re.sub(r'[.,]', '', count_str)
    else:
        # Si es decimal con coma, lo convertimos a punto
        count_str = count_str.replace(',', '.')

    try:
        return int(float(count_str) * multiplier)
    except ValueError:
        return 0


def extract_number(text: str) -> str:
    # Busca patrones como: 1,2 M / 30 / 3.000 / 1,5 millones
    match = re.search(r'[\d.,]+(?:\s?[kKmMbB]|(?:\s?(mil|millón|billón)))?', text)
    return match.group(0) if match else ''