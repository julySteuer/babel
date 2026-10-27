def exec_first_valid(*l):
    for value, method in l:
        if value is not None:
            return method(value)
    return None
