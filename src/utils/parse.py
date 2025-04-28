import re

def parse_number(text):
    text = text.lower().strip()
    
    text = re.sub(r'[^\d.,kKmM]', '', text)

    if 'm' in text:
        return int(float(text.replace('m', '').replace(',', '').replace('.', '.')) * 1_000_000)
    elif 'k' in text:
        return int(float(text.replace('k', '').replace(',', '').replace('.', '.')) * 1_000)
    else:
        return int(text.replace(',', '').replace('.', ''))
