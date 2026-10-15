"""Validador mínimo de esquema (subconjunto de JSON Schema), só biblioteca padrão.

O nó de formatação usa isto para garantir que a UI só recebe JSON no formato combinado.
Suporta: type, required, properties, additionalProperties=false, items, enum,
minLength, maxLength, minimum, maximum, minItems.
"""

TIPOS = {
    "object": dict, "array": list, "string": str,
    "integer": int, "number": (int, float), "boolean": bool,
}


class ErroValidacao(ValueError):
    pass


def validar(valor, esquema: dict, caminho: str = "$"):
    t = esquema.get("type")
    if t:
        py = TIPOS[t]
        # bool é subclasse de int em Python: não aceitar True onde se espera número
        if t in ("integer", "number") and isinstance(valor, bool):
            raise ErroValidacao(f"{caminho}: esperado {t}, veio boolean")
        if not isinstance(valor, py):
            raise ErroValidacao(f"{caminho}: esperado {t}, veio {type(valor).__name__}")
    if "enum" in esquema and valor not in esquema["enum"]:
        raise ErroValidacao(f"{caminho}: {valor!r} fora de {esquema['enum']}")
    if isinstance(valor, str):
        if len(valor) < esquema.get("minLength", 0):
            raise ErroValidacao(f"{caminho}: texto curto demais")
        if "maxLength" in esquema and len(valor) > esquema["maxLength"]:
            raise ErroValidacao(f"{caminho}: texto passa de {esquema['maxLength']} caracteres")
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if "minimum" in esquema and valor < esquema["minimum"]:
            raise ErroValidacao(f"{caminho}: {valor} < mínimo {esquema['minimum']}")
        if "maximum" in esquema and valor > esquema["maximum"]:
            raise ErroValidacao(f"{caminho}: {valor} > máximo {esquema['maximum']}")
    if isinstance(valor, dict):
        props = esquema.get("properties", {})
        for k in esquema.get("required", []):
            if k not in valor:
                raise ErroValidacao(f"{caminho}: falta o campo obrigatório '{k}'")
        if esquema.get("additionalProperties") is False:
            extra = set(valor) - set(props)
            if extra:
                raise ErroValidacao(f"{caminho}: campos não previstos {sorted(extra)}")
        for k, sub in props.items():
            if k in valor:
                validar(valor[k], sub, f"{caminho}.{k}")
    if isinstance(valor, list):
        if len(valor) < esquema.get("minItems", 0):
            raise ErroValidacao(f"{caminho}: poucos itens")
        if "items" in esquema:
            for i, item in enumerate(valor):
                validar(item, esquema["items"], f"{caminho}[{i}]")
    return True
