try:
    import readline
except ImportError:  # pragma: no cover
    readline = None


class GameCompleter:
    def __init__(self, handler):
        self.handler = handler
        self.matches = []

    def complete(self, _text: str, state: int) -> str | None:
        if readline is None:
            return None

        if state == 0:
            buffer = readline.get_line_buffer()
            self.matches = self.handler.get_completion_candidates(buffer)

        if state < len(self.matches):
            return self.matches[state]
        return None


def enable_command_completion(handler) -> GameCompleter | None:
    if readline is None:
        return None

    completer = GameCompleter(handler)
    readline.set_completer_delims("")
    readline.set_completer(completer.complete)
    readline.parse_and_bind("tab: complete")
    try:
        readline.parse_and_bind("set show-all-if-ambiguous on")
    except Exception:  # pragma: no cover
        pass
    return completer
