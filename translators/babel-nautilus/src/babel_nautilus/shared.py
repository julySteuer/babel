def make_nonterminal_str(nonterminal: str) -> str:
    return f"{{{nonterminal}}}"


def capitalize_name(name: str) -> str:
    if name[0].islower():
        return name[0].upper() + name[1:]
    return name


def check_nonterminal_reference(nonterm: str):
    if not nonterm[0].isupper():
        raise Exception(f"Malformed Nonterm Reference: {nonterm}")