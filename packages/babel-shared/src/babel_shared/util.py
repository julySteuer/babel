import itertools


def flatten[T](l: list[list[T]]) -> list[T]:
    return list(itertools.chain(*l))