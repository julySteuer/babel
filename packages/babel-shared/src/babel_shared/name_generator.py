"""
This might lead to problems with colission if another rule was initaliy named test0 or something. maybe initally put in BabelIr and check for all rules
TODO: Add initial hydration via ir so that if a names does appear it will get skipped
TODO: Make this `contextvar` so it does not behave as uncontrolably as globals tend to do
"""


class NameGenerator:
    def __init__(self):
        self.counter: dict[str, int] = {}

    def hydrate(self, name: str):
        if self.counter.get(name) is None:
            self.counter[name] = 0

    def generate_for(self, name: str) -> str:
        self.hydrate(name)
        child_name = f"{name}_{str(self.counter[name])}__GENERATED"
        self.counter[name] += 1
        return child_name


stateful_name_generator = NameGenerator()

__all__ = ["stateful_name_generator"]
